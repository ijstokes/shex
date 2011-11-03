# $Id: shex.py 1091 2011-11-03 03:25:49Z ijstokes $
# $HeadURL: https://ijstokes@developer.sbgrid.org/repos/nebiogrid/trunk/projects/shex/shex.py $
#
# Ian Stokes-Rees, ijstokes@spmetric.com, November 2009

"""
shex: Python shell extensions
-----------------------------

Project page: https://github.com/ijstokes/shex

The goal of the shex module is to compile common shell scripting commands into
a single, stand-alone Python module. These functions try to mimic shell
commands as closely as possible: sometimes this simply means creating aliases
for existing python functions, while other times existing functionality is
augmented to create a closer parallel to the shell command.

Functions generally operate in one default mode.  "dash" options for the
various commands are not currently supported but are on the TODO list.

Environment Variables
---------------------
SHEX_STRICT
SHEX_LIMITCHARS
PYLOG
PYLOG_DEST
PYLOG_FORMAT

Logging Messages
----------------
Shex includes a "basicConfig" logging instance that outputs to STDERR or
wherever PYLOG_DEST points to (special values STDOUT and STDERR will output
to standard output or error respectively).  The PYLOG level determines what
level of messages get output: DEBUG, INFO, WARN, ERROR, CRITICAL, EXCEPTION.

Errors and Exceptions
---------------------
The default configuration of shex and most (eventually all) functions is to
never throw an exception and allow processing to continue on a best-effort
basis.  This matches the paradigm found in shell scripting: provided the
syntax is correct, the failure of any given command does not result in the
script aborting with an error.

This behavior can be changed by setting the environment variable SHEX_STRICT
to True, or on a per-function basis with the "s" flag.  In this case, any
unexpected error (file doesn't exist, command fails, etc.) will result in
an exception being thrown.

Path Expansion
--------------
Any functions that expect a file or directory path will accept unix wildcards
and variable expansion, so '~/*/somedir/$VAR/*.py' is a valid path and will
be expanded to a list of possible full paths.  If only a single path is
expected and multiple paths are returned the function will exit with an
error.

Path Validation
---------------
By default, paths are checked to see if they contain valid characters taken
from the set FILE_CHARS.  Setting the environment variable SHEX_LIMITCHARS to
"True" will instead use a more restrictive valid character set (web-friendly)
Many functions also support a boolean flag "lc" (default:False).  If either
the global LIMITCHARS flag or the function-local flag are True, then path
validation will use the limited set of characters.

String Interpolation
--------------------
i(str) will substitute $foo with the string interpretation of foo taken from
the local and global variable space (namespace context)

j(str,d) will do the same thing, but only look for foo in the dictionary d

Function Catalog and Examples
-----------------------------
bg
bz2
cat
cd
chmod
chown
cp
curl
cwd
echo
env
gunzip
gzip
head
ln
ls
mkdir
mv
peek
popd
pushd
pwd
rm
sort
tail
tar
untar
wget

Contributors
------------
Ian Stokes-Rees
Caitlin Colgrove
Steve Jahl

"""

# TODO:
# Pipe from http://code.activestate.com/recipes/276960/
#      or   http://dev-tricks.net/pipe-infix-syntax-for-python

import  os
import  sys
import  gzip as py_gzip
import  tarfile
import  bz2 as py_bz2
import  zipfile
import  tempfile
import  inspect
import  string
import  re
import  stat

from    pwd         import getpwnam,getpwuid
from    grp         import getgrnam
from    os          import environ, chdir, getcwd, popen, popen2, popen3, popen4, \
                           tmpfile, link, makedirs, remove, \
                           rmdir, removedirs, rename, renames, symlink, kill, \
                           killpg, nice, times, getloadavg, getpid, getuid, geteuid, \
                           getegid, uname
from    subprocess  import Popen, PIPE
from    signal      import alarm, signal, SIGALRM, SIGKILL, SIGINT, SIG_DFL, SIG_IGN

from    os.path     import *
from    urllib      import *
from    urlparse    import urlparse
from    shutil      import *
from    commands    import *
from    socket      import gethostname
from    glob        import *
from    time        import *
from    shlex       import split as shsplit

import  logging
from    logging     import  debug, info, warning, error as err, critical, exception, \
                            log, disable, basicConfig, DEBUG, INFO, WARNING, ERROR, CRITICAL

from    threading   import Thread

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

DEFAULT_PYLOG = WARNING

# regex to use for path validation. More restrictive than standard Unix
FILE_CHARS          = "a-zA-Z0-9_ +.#%(),-"

# even more limited regular expression. To use this one, set SHEX_LIMITCHARS to True/yes/1 etc
# or set lc flag in function call to True
#TODO: add 
LIMIT_FILE_CHARS    = "a-zA-Z0-9_.-"

STRICT = False #if true, will raise exceptions and halt the program. Otherwise just prints
               #error message and continue
if environ.has_key("SHEX_STRICT"):
    if environ["SHEX_STRICT"][0] in "1TtyY":
        STRICT = True

LIMITCHARS = False
if environ.has_key("SHEX_LIMITCHARS"):
    if environ["SHEX_LIMITCHARS"][0] in "1TtyY":
            LIMITCHARS = True

LOG_LEVELS          = set(['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL', 'EXCEPTION'])
LOG_DEBUG_SET       = set(['DEBUG'])
LOG_INFO_SET        = set(['DEBUG', 'INFO'])
LOG_WARN_SET        = set(['DEBUG', 'INFO', 'WARN'])
LOG_ERROR_SET       = set(['DEBUG', 'INFO', 'WARN', 'ERROR'])
LOG_CRITICAL_SET    = set(['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'])
LOG_EXCEPTION_SET   = set(['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL', 'EXCEPTION'])

SECOND = 1
MINUTE = 60
HOUR   = 60  * MINUTE
DAY    = 12  * HOUR
WEEK   = 7   * DAY
MONTH  = 30  * DAY
YEAR   = 365 * DAY

KB     = 2**10
MB     = 2**20
GB     = 2**30
TB     = 2**40
PB     = 2**50
EB     = 2**60

(major, minor, patch, note, other) = sys.version_info
ON_POSIX = 'posix' in sys.builtin_module_names

procs   = [] # list of backgrounded processes

def enqueue_output(out, queue):
    for line in iter(out.readline, ''):
        queue.put(line)
    out.close()

def setlog():
    """ Sets up the logging environment """

    global major, minor

    log_fh = sys.stderr
    if environ.has_key("PYLOG_DEST"):
        if environ['PYLOG_DEST'] == 'STDOUT':
            log_fh = sys.stdout
        elif environ['PYLOG_DEST'] == 'STDERR':
            log_fh = sys.stderr
        else:
            log_fn = environ['PYLOG_DEST']
            if exists(log_fn):
                try:
                    log_fh = open(log_fn,'a')
                except:
                    log_fh = sys.stderr

    if environ.has_key("PYLOG"):
        if environ['PYLOG'] == 'DEBUG':
            loglevel = DEBUG
        elif environ['PYLOG'] == 'INFO':
            loglevel = INFO
        elif environ['PYLOG'] == 'WARN':
            loglevel = WARNING
        elif environ['PYLOG'] == 'ERROR':
            loglevel = ERROR
        elif environ['PYLOG'] == 'CRITICAL':
            loglevel = CRITICAL
        else:
            loglevel = DEBUG
            debug("Invalid setting for PYLOG [%s].  Defaulting to DEBUG." % environ['PYLOG'])
    else:
        loglevel = DEFAULT_PYLOG

    if environ.has_key("PYLOG_FORMAT"):
        pylog_format = environ['PYLOG_FORMAT']

    if ( major >= 3 or ( major == 2 and minor >= 5 )):
        if environ.has_key("PYLOG_FORMAT"):
            pylog_format = environ['PYLOG_FORMAT']
        else:
            pylog_format = "%(asctime)s:%(levelname)s:%(module)s:%(funcName)s:%(lineno)d:%(message)s"
        basicConfig(level=loglevel, stream=log_fh, format=pylog_format, datefmt="%s")
    elif ( major == 2 and minor >= 4 ):
        if environ.has_key("PYLOG_FORMAT"):
            pylog_format = environ['PYLOG_FORMAT']
        else:
            pylog_format = "%(asctime)s:%(levelname)s:%(module)s:%(lineno)d:%(message)s"
        basicConfig(level=loglevel, stream=log_fh, format=pylog_format, datefmt="%s")
    else:
        basicConfig()

setlog()

# Alias commands to standard Unix names

cd          = chdir
cwd         = getcwd
env         = environ
pwd         = getcwd
ln          = symlink
mv          = rename
hostname    = gethostname
date        = asctime

warn        = warning # short form for logging message

# initialize the directory stack with "here"
# This may or may not be a good idea.
dirstack = [cwd()]

level_str = os.environ.get("PYLOG","DEBUG")

# Python 2.3 compatible dictionary replacement using %(varname)s
def j(str, d):
    
    str_esc = re.sub(r"%","%%",str)
    # escape existing % characters
    str_mod = re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", str_esc)
    result = str_mod % d
    return result

# Python 2.3 compatible globals+locals replacement using %(varname)s
#def i(str):
#    d = {}
#    d.update(globals())
#    d.update(locals())
#    return j(str, d)
""" Perl/shell style strings with embedded variable references (from locals/globals)

Python 2.4 and above:

>>> FOO = 42
>>> d   = {'FOO': 42}
>>> i("substitute $FOO but leave $BAR") 
    'substitute 42 but leave $BAR'
>>> j("substitute $FOO but leave $BAR", d) 
    'substitute 42 but leave $BAR'

For Python 2.3, automatically convert $FOO into %(FOO)s to use standard string
interpolation, but requires all identifiers to be defined.

>>> FOO = 42
>>> d   = {'FOO': 42}
>>> i("substitute $FOO") 
    'substitute 42'
>>> j("substitute $FOO", d) 
    'substitute 42'

    """

def merge_vars(f=3, d={}):
    """ Merge all variables from 'f' levels back in the call stack into a single dictionary.
f frame depth to pull vars from call stack
d extra dictionary to merge at end
"""
    m = {}
    import inspect
    depth = min(f+1,len(inspect.stack()))
    while depth > 1:
        m.update(sys._getframe(depth).f_globals)
        m.update(sys._getframe(depth).f_locals)
        depth -= 1
    m.update(d)
    m.pop("self", "")
    return m

if (major >= 2) and (minor >= 4):
    # Features from Python 2.4 and above
    basicConfig(level=logging._levelNames[level_str], stream=sys.stderr,
                        format="%(asctime)s:%(levelname)s:%(module)s:%(lineno)d:%(message)s", datefmt="%s")
    # This does string interpolation using $foo, so '"Hello %s" % foo' can be written i("Hello $foo")
    # using string.Template is faster (so I'm told)
    # NOTE: Cannot do Perl-style list or dictionary resolution
    #ix = lambda _   : expand(string.Template(_).safe_substitute(sys._getframe(1).f_globals, **sys._getframe(1).f_locals))
    #i  = lambda _   : string.Template(_).safe_substitute(sys._getframe(1).f_globals, **sys._getframe(1).f_locals)
    #i2 = lambda _   : string.Template(_).safe_substitute(sys._getframe(2).f_globals, **sys._getframe(2).f_locals)
    #i3 = lambda _   : string.Template(_).safe_substitute(sys._getframe(3).f_globals, **sys._getframe(3).f_locals)
    ix = lambda _   : expand(string.Template(_).safe_substitute(merge_vars(1)))
    i  = lambda _   : string.Template(_).safe_substitute(merge_vars(1))
    i2 = lambda _   : string.Template(_).safe_substitute(merge_vars(2))
    i3 = lambda _   : string.Template(_).safe_substitute(merge_vars(3))
    j  = lambda t,d : string.Template(t).safe_substitute(d)
else:
    from sets import Set as set
    basicConfig()
    #ix  = lambda t   : expand(re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % sys._getframe(1).f_globals | sys._getframe(1).f_locals)
    #i   = lambda t   : re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % sys._getframe(1).f_globals | sys._getframe(1).f_locals
    #j   = lambda t,d : re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % d
    ix  = lambda t   : expand(re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % merge_vars(1))
    i   = lambda t   : re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % merge_vars(1)
    j   = lambda t,d : re.sub(r"\$([A-Za-z0-9_]+)", r"%(\1)s", re.sub(r"%","%%", t)) % d


def ls(p_raw=None, d=False, s=False, lc=False):
    """
    The equivalent of Unix ls, but does not list '.', '..'.  "d" is
    a falg with rough equivalence to the "-d" option and will not expand
    directories if set to True (default is False).  The exceptions is a bare
    ls() on the current directory which will not expand directories regardless
    of setting.

    Pre-conditions: p_raw is string that is a valid unix-style path, relative
    or absolute, and possibly including wildcards or variable names. p_raw can
    also be a list of such strings.  Post-conditions: none

    Return value: a list of existing files and directories fulfilling pattern
    p_raw

    Examples:
    ls() 
        returns [...contents of current directory...]
    ls(['~/*.txt','~/*.html'])
        returns a list of all files with extension .txt or .html in your home directory
    ls('dir/*')
        returns [...contents of directory dir...]

    Possible errors: none
    """

    flist = []

    if p_raw == None: # list contents of current directory only
        flist = clean_flist("*", s=s)
    else: # otherwise list contents of specified path/regex
        flist = clean_flist(p_raw, s=s)
        if not d:
            for e in flist:
                if isdir(e): # remove the entry and extend the list with the contents of the dir
                    flist.remove(e)
                    flist.extend(glob(expand("%s/*" % e)))

    flist.sort()

    return flist

# TODO: Implement equivalent of ls -Flad
#def ll(p_raw="*", s=False, lc=False):
ll = ls # for now, just alias ls

def rm(p_raw='', s=False, lc=False):
    """
    Unix rm. Will remove all regular files matching pattern p_raw (either a string or a list of
    strings). Does not remove directories - not an equivalent of rm -r.

    Pre-conditions: p_raw is a string or list of valid unix paths.
    Post-conditions: all regular files matching p_raw will be removed.
    Return value: none

    Examples:
    rm('home/file.txt')
        removes file file.txt from the subdirectory named home of the current directory (if the
        path home/file.txt exists)
    rm('*')
        removes everything in current directory

    Possible errors:
        no path provided - does nothing
        entry matching path is not a file - skips path
    """

    for entry in clean_flist(p_raw,s=s):
        if isfile(entry):
            remove(entry)
        else:
            if (s or STRICT):
                raise Exception, "Cannot remove [%s]: not a regular file." % entry 
            else:
                perror("Cannot remove [%s]: not a regular file." % entry)
                err("Cannot remove [%s]: not a regular file." % entry)

def mkdir(p_raw,s=False,lc=False):
    """
    Unix mkdir, but makes all intermediate directories as well if they don't already exist.

    Pre-conditions: p_raw is a string or list of strings of valid unix paths.
    Post-conditions: all directories along paths matching p_raw will be created.
    Return value: none

    Examples:
    mkdir(['~/docs','~/tmp'])
        makes directories 'docs' and 'tmp' in user's home directory
    mkdir('files/img')
        will create a directory 'files' in current directory if it doesn't exist, and create
        the directory 'img' inside of that.

    Possible errors:
        no path provided - does nothing
        python is unable to create a directory - skips path
        directory already exists - skips path
    """

    if not p_raw:
        if (s or STRICT):
            raise Exception, "Missing file argument in mkdir."
        else:
            perror("Missing file argument in mkdir.")
            err("Missing file argument in mkdir.")
        return

    if type(p_raw) != type(list()):
        p_raw = [p_raw]

    for dp in p_raw:
        full_dp = expand(dp)
        if not exists(full_dp):
            try:
                makedirs(full_dp)
            except Exception, e:
                if (s or STRICT):
                    raise e
                else:
                    perror("Cannot make directory [%s]" % full_dp)
                    err("Cannot make directory [%s]" % full_dp)
        else:
            if (s or STRICT):
                raise Exception, "Directory [%s] exists" % full_dp
            else:
                #pinfo("Directory [%s] exists - skipping mkdir" % full_dp)
                info("Directory [%s] exists - skipping mkdir" % full_dp)

def assert_exists(fp,s=False,lc=False):
    if not exists(fp):
        if (s or STRICT):
            raise Exception, "[%s] does not exist"
        else:
            perror("[%s] does not exist")
            err("[%s] does not exist")
        sys.exit(-1)

def pushd(dp,s=False,lc=False):
    """
    Unix pushd. Pushes current directory onto the global variable dirstack and changes
    directory to the new directory dp. If dp does not exist, pushd attempts to create it.

    Pre-conditions: dp is a single valid path name. It may contain wildcards and variables
    but only if they expand to a single path. 
    Post-conditions: if dp did not exist, it now does. The current directory is dp, and the
    top of dirstack is the previous directory.
    EDIT: no longer creates the directories - if directory doesn't exist, prints an error
    message
    Return value: none

    Examples:
    pushd('$HOME')
        pushes current directory and changes directory to the home directory
    pushd('..')
        pushes current directory and changes directory to the parent directory

    Possible errors:
        dp does not exist and python can't create it - does nothing
        cannot cd into directory (e.g. not world-executable) - does nothing
        dp expands to 0 or multiple paths - does nothing
    """
    expand_dp = clean_flist(dp,s=s)
    if len(expand_dp) > 1:
        if (s or STRICT):
            raise Exception, "Invalid path [%s]" % dp
        else:
            perror("Invalid path [%s]" % dp)
            err("Invalid path [%s]" % dp)
        return
    elif len(expand_dp)==0:
        if (s or STRICT):
            raise Exception, "No such file or directory [%s]" % dp
        else:
            warning("No such file or directory [%s]" % dp)
        return

    dp = expand_dp[0]

#   if not exists(dp):
#       try: 
#           makedirs(dp)
#       except Exception, e:
#           if (s or STRICT):
#               raise e
#           else:
#               perror("Cannot create directory [%s]." % dp)  
#               err("Cannot create directory [%s]." % dp)  
#           return 
    info("%s -> %s" % (pwd(), dp))

    try:
        cur = pwd() 
        chdir(dp)
        dirstack.append(cur)
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot pushd [%s]." % dp) 
            err("Cannot pushd [%s]." % dp) 

def popd(s=False,lc=False):
    """
    Unix popd. Returns to the directory on top of dirstack, If dirstack is empty, it 
    does nothing.

    Pre-conditions: none
    Post-conditions: if dirstack is not empty, top directory is popped and becomes working
    directory. Otherwise, nothing changes.
    Return value: none

    Examples:
    popd()

    Possible errors: none
    """
    if len(dirstack) >= 1:
        info("%s <- %s" % (dirstack[-1], basename(pwd())))
        dp = dirstack.pop()
        try:
            chdir(dp)
        except Exception, e:
            if (s or STRICT):
                raise e
            else:
                perror("Cannot popd [%s]." % dp)
                err("Cannot popd [%s]." % dp)
    else:
        warning("Directory stack empty on popd.  In [%s]." % cwd())

def peek():
    """
    Returns the top entry on the stack without popping. If dirstack is empty, returns
    '.' for the current directory.
    
    Pre-conditions: none
    Post-conditions: none
    Return value: the top of dirstack or '.'

    Example:
    prev_dir = peek()

    Possible errors: none
    """

    if len(dirstack) > 0:
        return dirstack[-1]
    else:
        return "."

def cp(raw_src, raw_dst, s=False, lc=False):
    """
    Unix cp -r. Copies a file, directory, or lists of files and directories to raw_dst. 

    Pre-conditions: src must be a string or list of valid unix paths that can expand to any number of 
    entries, but if it expands to more than one, raw_dst must be a directory. raw_dst may contain wildcards,
    but must only expand to one value.
    Post-conditions: all existing files/directories from src are copied to dst
    Return value: none

    Examples:
    cp('docs','docs_backup')
        recursively copies all files from docs to a new directory called docs_backup, unless docs_backup
        already exists, in which case files will be copied to docs_backup/docs
    cp('*.png','img')
        copies all files in the current directory with extension png to existing directory img
    
    Possible errors:
        copying multiple files or a directory to a single file - does nothing
        raw_dst expands to multiple locations - does nothing
        copying a directory to a target that exists - skips entry
        python copy function fails - skips entry
    """

    src = expand(i2(raw_src))
    dst = expand(i2(raw_dst))

    if type(dst) == type(list()):
        if (s or STRICT):
            raise Exception, "Invalid cp destination [%s]" % raw_dst
        else:
            perror("Invalid cp destination [%s]" %raw_dst)
            err("Invalid cp destination [%s]" %raw_dst)
        return

    clean_src = clean_flist(src, s=s)

    # Can only copy multiple sources to dst if dst is an existing directory, otherwise fail
    if len(clean_src) > 1 and not isdir(dst):
        if (s or STRICT):
            raise Exception, "[%s] is not a directory, cannot copy multiple entries" % dst
        else:
            perror("[%s] is not a directory, cannot copy multiple entries" % dst)
            err("[%s] is not a directory, cannot copy multiple entries" % dst)
    else:
        for item in clean_src:
            debug("atomic cp %s %s" % (item, dst))
            item = i2(item)
            if isfile(item):
                try:
                    debug("copy2 item [%s] to [%s]" % (item, dst))
                    copy2(item,dst)
                except Exception, e:
                    if (s or STRICT):
                        raise e
                    else:
                        warning("Copy failed: %s %s %s" % (pwd(), item, dst))
            elif isdir(item):
                if isfile(dst):
                    if (s or STRICT):
                        raise Exception, "Cannot copy directory [%s] to file [%s]" % (item, dst)
                    else:
                        perror("Cannot copy directory [%s] to file [%s]" % (item, dst)) 
                        err("Cannot copy directory [%s] to file [%s]" % (item, dst)) 
                elif isdir(dst):
                    dir_dst = "%s/%s" % (dst, basename(item))
                    if not exists(dir_dst):
                        try:
                            debug("copytree dir [%s] to [%s]" % (item, dir_dst))
                            copytree(item, dir_dst)
                        except Exception, e:
                            if (s or STRICT):
                                raise e
                            else:
                                warning("Copy failed: %s %s %s" % (pwd(), item, dir_dst))
                    else:
                        if (s or STRICT):
                            raise Exception, "[%s] destination already exists" % (dir_dst)
                        else:
                            perror("[%s] destination already exists" % (dir_dst))
                            err("[%s] destination already exists" % (dir_dst))
                else:
                    try:
                        debug("copytree item [%s] to [%s]" % (item, dst))
                        copytree(item, dst)
                    except Exception, e:
                        if (s or STRICT):
                            raise e
                        else:
                            warning("Copy failed: %s %s %s" % (pwd(), item, dst))
    
def cmp_copy(master, replica, s=False, lc=False):
    " Compare master to replica.  If not the same real path (or if replica does not exist), copy master over replica "
    debug(dirname(replica))

    if (not isfile(replica)) or (realpath(abspath(master)) != realpath(abspath(replica))):
        if not exists(dirname(replica)):
            debug("About to create directories for path: [%s]" % dirname(replica))
            makedirs(dirname(replica))
        cp(master, replica,s=s)
        
def curl(url, fn=None, s=False, lc=False):
    """
    Unix curl/wget. Downloads a file/direcroty from an url.

    Pre-conditions: url is a valid url
    Post-conditions: file will be downloaded and stored at the location fn. If fn is
    an existing directory, the contents will be stored under the basename of the url in that 
    directory. Otherwise, a new file will be created to hold those contents.
    Return value: none

    Examples:
    curl("http://www.example.com/css/example.css")
        stores the file example.css in the current directory
    curl("http://www.mysite.org/facts.txt", "info")
        if 'info' is a directory, stores 'facts.txt' in info. Otherwise, stores 'facts.txt' 
        in a file named 'info' in the current directory.

    Possible errors:
        unable to retrieve from url (e.g. invalid url) - does nothing
    """
    if fn == None or isdir(fn):
        url_parts = urlparse(url)
        if fn == None:
            fn = basename(url_parts.path)
        else:
            fn = "%s/%s" % (fn, basename(url_parts.path))

    debug("urlretrieve(%s, %s)" % (url, fn))
    try:
        urlretrieve(url, fn)
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot retrieve file from url [%s]." % (url))
            err("Cannot retrieve file from url [%s]." % (url))

wget = curl # alias wget to be the same as curl

def fixpath(p):
    """ create any directories in the path that don't already exist """
    if p.find("/") >= 0:
        d = dirname(p)
        mkdir(d)
    
def tac(arg, bufsize=8192):
    """ tac: return lines of file in reverse order
ActiveState Code Recipe: http://code.activestate.com/recipes/496941/
"""
    fh          = open(arg, 'rb')
    fh.seek(0, 2) # go to the end
    leftover    = ''
    while fh.tell():
        if fh.tell()<bufsize:
            bufsize = fh.tell()
        fh.seek(-bufsize, 1)
        in_memory   = fh.read(bufsize) + leftover
        fh.seek(-bufsize, 1)
        lines       = in_memory.split('\n')
        for i in reversed(lines[1:]):
            yield i
        leftover = lines[0]
    fh.close()
    yield leftover

def echo(txt, raw_dst=None, append=False, s=False, lc=False):
    """
    Unix echo. Expands variables in a string and optionally writes them to a file.
 
    Pre-conditions: txt is a string or a list of strings
    Post-conditions: none
    Return value: if dst is None, then the expanded and concatenated strings,
                    otherwise this is output to dst

    Example:
    foo = 42
    bar = "out.dat"
    echo("The value of foo is $foo")
        returns "The value of foo is 42"
    echo("The value of foo is $foo", "/tmp/$bar")
        writes "The value of foo is 42" to the file /tmp/out.dat

    Possible errors:
        dst is an invalid destination - returns an exception
    """
    
    if raw_dst:
        dst = expand(i2(raw_dst))
        fixpath(i2(dst))
        if append:
            out_fh = open(dst,'a')
        else:
            out_fh = open(dst,'w')

        if len(txt) > 0:
            out_fh.write(i2(txt))
            out_fh.close()
        return
    else:
        out = i2(txt)
        print out

# FIXME: needs to background the command
def bg(cmds, out=sys.stdout, err=sys.stderr):
    if type(cmds) != type(list()):
        cmds_list = [cmds]
    else:
        cmds_list = cmds

    for cmd in cmds:
        if type(cmd) == type(tuple()) and len(cmd) >= 2:
            cmd_out = cmd[1]
        else:
            cmd_out = out
        if type(cmd) == type(tuple()) and len(cmd) >= 3:
            cmd_err = cmd[2]
        else:
            cmd_err = err
        c(cmd, stdout=cmd_out, stderr=cmd_err, bg=True)        

def cat(raw_src, raw_dst=None, append=False, s=False, lc=False):
    """
    Unix cat. Returns the contents of a file or list of files.
 
    Pre-conditions: src is a string or a list of valid unix paths to files.
    Post-conditions: none
    Return value: a list in which each entry is a line, terminated by a newline, of
    the files in src

    Example:
    cat("info.txt")
        returns a list of the contents of info.txt: ['line 1\n','line 2\n'...]

    Possible errors:
        an entry in src is a directory - skips entry
        cannot open an entry in src - skips entry
    """
    lines = []
    
    src = expand(i2(raw_src))
    files = clean_flist(src, s=s)
    
    if raw_dst:
        dst = expand(i2(raw_dst))
        fixpath(dst)
        if append:
            out_fh = open(dst,'a')
        else:
            out_fh = open(dst,'w')
        
    for f in files:
        try:
            fh = open(f)
            if raw_dst:
                out_fh.write(fh.read())
            else:
                lines.extend(fh.readlines())
            fh.close()
        except Exception, e:
            if (s or STRICT):
                raise e
            else:
                perror("Cannot read file [%s]" % file)
                err("Cannot read file [%s]" % f)

    if raw_dst:
        out_fh.close()
        return
    else:
        return lines

def unzip(zip_fp, dst=".", ext=".zip",s=False,lc=False):
    zip_fp = expand(zip_fp)

    if not exists(zip_fp):
        if (s or STRICT):
            raise Exception, "File [%s] not found" % zip_fp
        else:
            err("File [%s] not found" % zip_fp)
        return
    if not zip_fp.endswith(ext):
        if (s or STRICT):
            raise Exception, "gunzip: File [%s] expected to have [%s] extension" % (zip_fp, ext)
        else:
            err("gunzip: File [%s] expected to have [%s] extension" % (zip_fp, ext))
        return

    try:
        zip_obj      = zipfile.ZipFile(zip_fp, 'r')
        for m in zip_obj.infolist():
            zip_obj.extract(m,dst) # FIXME even this is Python2.6 only
        # require using ZipInfo obj file name, create dir, open file to write
        # and then extract_fh.write(zip_obj.read(m))
        # zip_obj.extractall() Python 2.6 onwards
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot gunzip file [%s] [%s]" %(zip_fp,e))
            err("Cannot gunzip file [%s] [%s]" %(zip_fp,e))
        return

#FIXME: um...
def gunzip(zip_fp, dst=".", ext=".gz",s=False,lc=False):
    zip_fp = expand(zip_fp)

    if not exists(zip_fp):
        if (s or STRICT):
            raise Exception, "File [%s] not found" % zip_fp
        else:
            perror("File [%s] not found" % zip_fp)
            err("File [%s] not found" % zip_fp)
        return
    if not zip_fp.endswith(ext):
        if (s or STRICT):
            raise Exception, "gunzip: File [%s] expected to have [%s] extension" % (zip_fp, ext)
        else:
            perror("gunzip: File [%s] expected to have [%s] extension" % (zip_fp, ext))
            err("gunzip: File [%s] expected to have [%s] extension" % (zip_fp, ext))
        return

    ext_idx  = zip_fp.find(ext)
    unzip_fp = zip_fp[0:ext_idx]

    try:
        zip_fh      = py_gzip.open(zip_fp, 'r')
        unzip_fh    = open("%s/%s" % (dst, unzip_fp), 'w')
        unzip_fh.write(zip_fh.read())
        unzip_fh.close()
        zip_fh.close()
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot gunzip file [%s] [%s]" %(zip_fp,e))
            err("Cannot gunzip file [%s] [%s]" %(zip_fp,e))
        return

def tar(tar_fp, src, ext=".tar", mode="w", s=False, lc=False):
    if not tar_fp.endswith(ext): # try to guess the extension and mode
        for (ext_alt, mode_alt) in [(".tgz", "w:gz"), (".tar.gz", "w:gz"), (".tar.bz2", "w:bz2")]:
            if tar_fp.endswith(ext_alt):
                debug("File [%s] has extension [%s]" % (tar_fp, ext_alt))
                ext  = ext_alt
                mode = mode_alt

    clean_src = clean_flist(src,s=s)
    #TODO: check tar_fp to see that it's only one place
    tar_fp = expand(tar_fp)
  
    try:
        info("opening tar file [%s] with mode [%s]" % (tar_fp, mode))
        tar_obj = tarfile.open(tar_fp, mode)
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot open file [%s]." % tar_fp)
        return

    for f in clean_src:
        tar_obj.add(f)
    tar_obj.close()

def bz2(src, dst, s=False ,lc=False):
    try:
        dst_fh = py_bz2.open(dst,"w")
        src_fh = open(src,"r")
        dst_fh.write(src_fh.read())
        dst_fh.close()
        src_fh.close()
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("%s" %e)
            err("%s" %e)

# TODO
def gzip(src, dst,s=False,lc=False):
    pass

def untar(tar_fp, dst=".", ext=".tar", mode="r", s=False, lc=False):
    tar_fp = expand(tar_fp)
    if not exists(tar_fp):
        if (s or STRICT):
            raise Exception, "File [%s] not found"
        else:
            perror("File [%s] not found" % tar_fp)
            err("File [%s] not found" % tar_fp)
        return

    if not tar_fp.endswith(ext): # try to guess the extension and mode
        for (ext_alt, mode_alt) in [(".tgz", "r:gz"), (".tar.gz", "r:gz"), (".tar.bz2", "r:bz2")]:
            if tar_fp.endswith(ext_alt):
                debug("File [%s] has extension [%s]" % (tar_fp, ext_alt))
                ext  = ext_alt
                mode = mode_alt

    try:
        pdebug("attempt untar: [%s] mode: [%s]" % (tar_fp, mode))
        tar_obj = tarfile.open(tar_fp, mode)
        pdebug("dst: [%s]" % dst)
        for m in tar_obj.getmembers():
            tar_obj.extract(m,dst)
        #tar_obj.extractall(dst) # extractall is from Python 2.5 onwards
        tar_obj.close()
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot untar file [%s] in mode [%s]" % (tar_fp,mode))
            err("Cannot untar file [%s] in mode [%s]" % (tar_fp,mode))
        return
    
def fsplit(in_fp, maxlines, maxsetcount=0, pad=3, prefix="", suffix="",s=False,lc=False):
    pattern = "%s%0" + str(pad) + "d%s"
    files   = []

    in_fp = expand(in_fp)

    try:
        in_fh   = open(in_fp)
    except Exception, e:
        if (s or STRICT):
            raise e
        else:
            perror("Cannot open file [%s]" %in_fp)
            err("Cannot open file [%s]" %in_fp)
        return

    idx     = 0
    set_cnt = 0

    for line in in_fh:
        if set_cnt == 0:
            out_fp = pattern % (prefix, idx, suffix)    
            try:
                out_fh = open(out_fp, "w")
            except Exception, e:
                if (s or STRICT):
                    raise e
                else:
                    perror("Split failed: cannot open file [%s]" %out_fp)
                    err("Split failed: cannot open file [%s]" %out_fp)
                return
            files.append(out_fp)

        out_fh.write(line)
        set_cnt += 1
        if set_cnt == maxlines:
            out_fh.close()
            set_cnt = 0
            idx += 1
    out_fh.close() # close the last set, which may not have reached "maxlines"
    return files

def rm_pat(flist):
    if type(flist) != type(list()):
        flist = [flist]
    for pattern in flist:
        for file_entry in glob(expand(pattern)):
            if isfile(file_entry): rm(file_entry)
            
now = time

def sort(p_raw,s=False,lc=False):
    """
    Unix sort. Sorts the lines of the files in the expansion of p_raw into alphabetical 
    order.

    Pre-conditions: p_raw is a string or list of valid unix paths, possibly containing 
    wildcards or variables.
    Postconditions: none 
    Return value: a list of the lines in the files in alphabetical order.

    Example:
    sort("names.txt")
        returns list of lines of names.txt in alphabetical order
    sort(['names1.txt','names2.txt'])
        returns the combined lines of names1.txt an names2.txt in sorted order

    Possible errors:
        if no file is provided - does nothing
    """

    clean_list = clean_flist(p_raw,s=s)
    lines = []
    
    for filename in clean_list:
        fh = open(filename,"r")
        lines.extend(fh.readlines())
        fh.close()

    lines.sort()
    return lines

def chmod(mode_raw, p_raw, s=False, lc=False):
    """
    Unix chmod. Changes the mode of a file, directory, or list of files and directories, but 
    does not recursively act on directories.

    Pre-conditions: mode is a valid string matching the expression ^[ugoa]+[+-=][rwxX]+ and 
    p_raw is a valid string or list of unix paths
    Post-conditions: mode on all files/directories matching p_raw will be changed to add/
    subract permissions from certain users.
    Return value: none

    Examples:
    chmod("o-x","script.py")
        removes "execute" permission for "other" on file script.py
    chmod("u=rx","dir")
        sets permissions for "user" to "read" and "write"

    Possible errors:
        invalid mode - does nothing
    """
    
    if type(mode_raw) != type(list()):
        mode_raw   = mode_raw.split()

    if type(p_raw) != type(list()):
        p_raw   = p_raw.split()
    
    p_list  = map(i2, p_raw)
    p_list  = map(expand, p_list)
    clean_list = clean_flist(p_list, s=s)
    
    for f in clean_list:
        cur_mode = os.stat(f).st_mode   
 
        for mode in mode_raw:
            ex = re.match("^(?P<ref>[ugoa]*)(?P<op>[+-=])(?P<perm>[rwxX]*)$", mode)
            if not ex:
                if (s or STRICT):
                    raise Exception, "Invalid mode [%s]" % mode
                else:
                    perror("Invalid mode [%s]" % mode)
                    err("Invalid mode [%s]" % mode)
                continue

            new_part = 0
            new_mode = cur_mode % 8**3

            for char in ex.group('perm'):
                if char == 'r':
                    new_part |= 4
                elif char == 'w':
                    new_part |= 2
                elif char == 'x':
                    new_part |= 1
                elif char == 'X':
                    if isdir(f):
                        new_part |= 1

            if ex.group('op') == '=':
                new_mode = 0
     
            u = new_part << 6
            g = new_part << 3
            o = new_part 
            a = u | g | o

            for char in ex.group('ref'):
                if ex.group('op') == '+' or ex.group('op') == '=':
                    new_mode |= eval(char)
                elif ex.group('op') == '-':
                    new_mode &= ~eval(char)

            debug("Changing [%s] to [%o]" % (f, new_mode))
            os.chmod(f, new_mode)

def chown(user,group,p_raw,s=False,lc=False):
    """
    Unix chown. Changes the ownership of files, directories, or a list of files and
    directories to that of user and group, but does not recursively act on directories.
    
    Pre-conditions: user and group must be valid users and groups. p_raw must be a valid 
    file, directory, or list of files and directories.
    Chown must be run as root.
    
    Examples:
        chown("joe", "staff", "file.txt")
            changes UID and GID of file.txt to joe and staff respectively.
        chown("joe", "staff", ["file.txt", "A_folder", "script.py"])
            changes UID and GID of file.txt, A_folder, and script.py to joe and staff respectively.
    Possible Errors:
        not root - does nothing
        invalid user - does nothing
        invalid group - does nothing
        invalid file or directory name - does nothing.
    
    """
    clean_list = clean_flist(p_raw,s=s)
    try:
        uid = getpwnam(user).pw_uid
        debug(uid)
    except KeyError, k:
        if (s or STRICT):
            raise k
        else:
            err("No such username [%s]" % user)
        return
    try:
        gid = getgrnam(group).gr_gid
        debug(gid)
    except KeyError, k:
        if (s or STRICT):
            raise k
        else:
            err("No such group [%s]" % group)
        return

    for f in clean_list:
        os.chown(f,uid,gid)

def head(src, l=10, s=False,lc=False):
    """
    Unix head. Returns the first 10 lines of a file in a list. The number
    of lines printed can also be defined with n.

    Pre-conditions: src must be a valid file. If n is defined,
    it must be a positive number.

    Example:
    head("message.txt")
        returns the first 10 lines of the file in a list.
    head("*.txt", l=3)
        returns the first 3 lines of of all .txt files

    Possible errors:
        if no file is provided - does nothing
        negative l is provided - does nothing
    """
    
    clean_src = clean_flist(src,s=s)

    if l < 0:
        if (s or STRICT):
            raise Exception, "Negative number of lines"
        else:
            perror("Negative number of lines")
            err("Negative number of lines")
        return

    for f in clean_src:
        try:
            fh = open(f,"r")
            if len(clean_src) > 1:
                yield "========== %s" % f
            for i in range(0, l):
                line = fh.readline()
                if line:
                    yield line
                else:
                    break
            fh.close()
        except Exception, e:
            if (s or STRICT):
                raise e
            else:
                perror("Could not read file [%s] - skipping" % f)
                err("Could not read file [%s] - skipping" % f)
            debug("%s", e)

def tail(src, n=10,s=False,lc=False):
    """
    Unix tail. Returns the last ten lines of a file in a list. The number
    of lines can also be defined by using n.
    
    Pre-conditions: src must be a valid file. If n is defined,
    it must be a positive number
    
    Examples:
        tail("script.py")
            returns the last ten lines of a file in a list
        tail("script.py", n="3")
            returns the last three lines of a file in a list
    """
    clean_src = clean_flist(src,s=s)
    lines = []

    if n < 0:
        if (s or STRICT):
            raise Exception,"Negative number of lines"
        else:
            perror("Negative number of lines.") 
            err("Negative number of lines.") 
        return
    
    for f in clean_src:
        try:
            fh = open(f,"r")
            cur_lines = fh.readlines()
            fh.close()
        except Exception, e:
            if (s or STRICT):
                raise e
            else:
                perror("Cannot read file [%s] - skipping" % f)
                err("Cannot read file [%s] - skipping" % f)

        if len(cur_lines) <= n:
            lines.extend(cur_lines)
        else:
            lines.extend(cur_lines[-1*n:])

    return lines
 
def grep(regex, p_raw, m=None, s=False, lc=False):
    """
        Search a file or list of files for the specified regex or list of
        regexes, returning all matching lines.
    """
    clean_src = clean_flist(p_raw,s=s)
    results = []
    if type(regex) == type(list()):
        regex_list = regex
    else:
        regex_list = [regex]
        
    match_cnt = 0
    for src in clean_src:
        try:
            fh = open(src)
        except Exception, e:
            if (s or STRICT):
                raise e
            else:
                perror("Cannot open file [%s]." %src)
                err("Cannot open file [%s]." %src)
            continue
        for line in fh:
            line_cnt = 0
            for re_tmp in regex_list:
                # TODO: regexes should be compiled once, not once per line per regex!
                if re.search(re_tmp, line) != None:
                    results.append(line)
                    line_cnt += 1
                    continue

            if m and line_cnt > 0:
                match_cnt += 1
                if match_cnt >= m:
                    break

        fh.close()

        if m and match_cnt >= m:
            break
            
    return results

def grept(regex, p_raw,s=False,lc=False):
    """
        Search a string or list of strings for the specified regex or list of
        regexes, returning all matching lines.
    """
    results = []
    if type(regex) == type(list()):
        regex_list = regex
    else:
        regex_list = [regex]

    if type(p_raw) == type(list()):
        str_list = p_raw
    else:
        str_list = [p_raw]
        
    for entry in str_list:
        for line in entry.split('\n'):
            for re_tmp in regex_list:
                if re.search(re_tmp, line) != None:
                    results.append(line)
                    continue
    return results
        
def findFile(seekName, path, implicitExt=''):
    """Given a pathsep-delimited path string, find seekName.
    Returns path to seekName if found, otherwise None.
    Also allows for files with implicit extensions (eg, .exe), but
    always returning seekName as was provided.
    >>> findFile('ls', '/usr/bin:/bin', implicitExt='.exe')
    '/bin/ls'
    """
    if os.path.isfile(seekName) or \
            (implicitExt and os.path.isfile(seekName + implicitExt)):
        # Already absolute path.
        return seekName
    for p in path.split(os.pathsep):
        candidate = os.path.join(p, seekName)
        if os.path.isfile(candidate) or \
            (implicitExt and os.path.isfile(candidate + implicitExt)):
            return candidate
    return None

last_exitcode = 0
timeout = False

# taken from http://stackoverflow.com/questions/1191374/subprocess-with-timeout
def c(args, cwd=None, env=None, stdin=None, shell=False, kill_tree=True, t=None, ex=False, m=True):
    '''
    Run a command with a timeout after which it will be forcibly
    killed.

    t   timeout [None]
    ex  throw exception on error or timeout [False]
    m   merge STDERR and STDOUT [True]
    '''
    # With thanks to StackOverflow, in particular:
    # http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python

    class Alarm(Exception):
        pass

    def alarm_handler(signum, frame):
        raise Alarm

    def sigstop(signal, frame):
        p.terminate()
        if p.poll() == None:
            sleep(0.1)
            if p.poll() == None:
                p.kill()

    q_out = Queue()
    q_err = Queue()
    full_stdout = []
    full_stderr = []
    for cmd in args.split(";"):
        try:
            parts = shsplit(cmd.replace('\n',' '))
            
            #debug("executable: %s\n" % parts[0] + "args: %s\n" % parts + "shell: %s\n" % shell + "cwd: %s\n" % cwd + "stdout: %s\n" % PIPE + "stderr: %s\n" % PIPE + "env: %s\n" % env)
            p = Popen(executable=parts[0], args=parts, shell=shell, cwd=cwd, stdin=stdin, stdout=PIPE, stderr=PIPE, env=env, bufsize=1, close_fds=ON_POSIX)
            t_out = Thread(target=enqueue_output, args=(p.stdout, q_out))
            t_err = Thread(target=enqueue_output, args=(p.stderr, q_err))
            t_out.daemon = True
            t_err.daemon = True
            t_out.start()
            t_err.start()

            if t != None:
                signal(SIGALRM, alarm_handler)
                alarm(t) # set alarm

            signal(SIGINT, sigstop)

            while p.poll() == None: # Process hasn't finished yet
                output = False
                try:
                    line = q_err.get_nowait() # or q.get(timeout=.1)
                except Empty:
                    pass # do nothing
                else: # got line
                    output = True
                    sys.stderr.write(line)
                    full_stderr.append(line.strip())
                try:
                    line = q_out.get_nowait() # or q.get(timeout=.1)
                except Empty:
                    pass # do nothing
                else: # got line
                    output = True
                    sys.stdout.write(line)
                    full_stdout.append(line.strip())
                if not output:
                    sleep(0.1) # Wait 100 ms if there was no output.

            if t != None:
                alarm(0) #disable alarm

        except Alarm:
            pids = [p.pid]
            if kill_tree:
                pids.extend(get_process_children(p.pid))
            for pid in pids:
                kill(pid, SIGKILL)
            if ex:
                last_exitcode = 137
                raise Exception("Process timeout after %d: [%s]" % (t, args))
            last_exitcode   = 137
            timeout         = 137
            if m:
                return [], ["MULTI TIMEOUT after %d seconds" % t, cmd], 137
            else:
                return [], ["TIMEOUT after %d seconds" % t], 137
        except OSError, e:
            last_exitcode = -3
            if ex:
                raise Exception("Process failed [%s]" % args)
            if m:
                return [], ["MULTI COMMAND FAILED", cmd, str(e)], last_exitcode
            else:
                return [], ["COMMAND FAILED", cmd, str(e)], last_exitcode
        if ex:
            last_exitcode = -1
            raise Exception("Process non-zero exit %d: [%s]\nSTDOUT:\n%s\nSTDERR:\n%s" % (timeout, args, stdout, stderr))

        last_exitcode = p.returncode

    signal(SIGINT, SIG_DFL)

    # flush stderr and stdout queues
    while not q_err.empty():
        line = q_err.get()
        sys.stderr.write(line)
        full_stderr.append(line.strip())
    while not q_out.empty():
        line = q_out.get()
        sys.stdout.write(line)
        full_stdout.append(line.strip())
    sys.stdout.flush()
    sys.stderr.flush()

    return full_stdout, full_stderr, last_exitcode

def get_process_children(pid):
    p = Popen('ps --no-headers -o pid --ppid %d' % pid, shell = True,
              stdout = PIPE, stderr = PIPE)
    stdout, stderr = p.communicate()
    return [int(p) for p in stdout.split()]

# FIXME: This currently does not work
def cX(cmds, stdin=None, stdout=PIPE, stderr=PIPE, aslist=True, bg=False):
    "Execute cmd through the shell and return list of lines of output, unless aslist==False"
    if cmds == "" or cmds == None:
        return
    if type(cmds) != type(list()):
        cmds_list = [cmds]
    else:
        cmds_list = cmds

    if aslist:
        output = []
    else:
        output = ""

    for cmd in cmds_list:
        if type(cmd) == type(tuple()) and len(cmd) >= 2:
            cmd_out = cmd[1]
            if type(cmd_out) == type("a"):
                try:
                    cmd_out = open(cmd_out,'w')
                except:
                    cmd_out = stdout
        else:
            cmd_out = stdout
        if type(cmd) == type(tuple()) and len(cmd) >= 3:
            cmd_err = cmd[2]
            if type(cmd_err) == type("a"):
                try:
                    cmd_err = open(cmd_err,'w')
                except:
                    cmd_err = stderr
        else:
            cmd_err = stderr
        if type(cmd) == type(tuple()):
            cmd = cmd[0]
        exp_cmd = []
        for p in cmd.split(" "):
            # FIXME: We'd like to do glob expansion, but this only works for
            #       arguments that are files that exist, otherwise the argument
            #       just disappears
            #exp_cmd.extend(glob(expand(p)))
            exp_cmd.append(expand(p))

        exp_cmd[0] = findFile(exp_cmd[0],os.environ['PATH'])
        if exp_cmd[0] == None or not exists(exp_cmd[0]):
            err("executable [%s] not found in current directory [%s] or in PATH (orig cmd: [%s])" % (exp_cmd[0], pwd(), cmd))
            err("PATH: [%s]" % "\n".join(os.environ['PATH'].split(":")))
            continue

        mode = os.stat(exp_cmd[0])[0]
        # check if execute bit is set for at least one of USR, GRP, or OTH
        if not (stat.S_IXUSR & mode or stat.S_IXGRP & mode or stat.S_IXOTH & mode):
            err("chmod a+x [%s] failed -- execution will likely fail")

        #(status, raw_output) =  getstatusoutput(cmd)
        debug("starting process: [%s]" % " ".join(exp_cmd))
        proc = Popen(exp_cmd, stdin=stdin, stdout=cmd_out, stderr=cmd_err)
        if bg: # background job.  Add to list and continue
            procs.append(proc)
            output.append(proc.pid)
        else:
            (cmd_out, cmd_err) = proc.communicate()

            if cmd_err != None and cmd_err != "":
                debug(cmd_err)

            if cmd_out != None:
                if aslist:
                    output.extend(cmd_out.split("\n"))
                else:
                    output += cmd_out

    return output
    
def bgwait(pids=None, interval=2, wait_timeout=None):
    """
Wait for specified backgrounded processes to finish.  If no PIDs specified
(string list, space separated list, or int list all accepted), then all
background processes are considered.  Between checks, bgwait will sleep for
interval seconds (default 2), up to wait_timeout (default 48 hours).
    """

    check_procs = []

    if wait_timeout == None: # default to 48 hours
        wait_timeout = 2 * DAY

    if pids: # build list of procs to check from specified pids
        if type(pids) != type(list()):
            pids_list = [pids]
        else:
            pids_list = pids.split()
        for pid in pids_list:
            try:
                int(pid)
            except:
                pids_list.delete(pid)

        for p in procs:
            if p.returncode: # this proc has finished, so go to next
                procs.delete(p)
                continue
            for pid in pids_list: # see if proc is in check list
                if p.pid == int(pid):
                    check_procs.append(p)
                    pids_list.delete(pid) # remove it from future checks
                    break # stop looking for a match for this proc
    else: # build list of procs to check from all procs
        for p in procs:
            if not p.returncode:
                check_procs.append(p)
            else: # process finished, remove from job list
                procs.delete(p)

    wait_start = timestamp()
    while len(check_procs) > 0 and (timestamp() - wait_start < wait_timeout):
        sleep(interval)
        for p in check_procs:
            if p.returncode:
                check_procs.delete(p) # process finished, remove from list

def touch(fp):
    """ Will create a file that doesn't exist, and won't erase a file that is
        already there, but it DOES NOT (currently) update the timestamp on a
        filethat already exists
    """
    fh = open(fp,'a')
    fh.close()

#TODO: This is broken and currently does not work.
m = {}
def search(regex, s):
    """ search for regex in string s and assign result to persisted match dictionary m.
        return True if match occurs, False otherwise. """
    result = False
    try:
        m = {} # reset m to an empty dictionary
        m = re.search(regex,s)
        if m != None:
            result = True
    except:
        pass
    return result

def dateutc():
    return asctime(gmtime())

def timestamp():
    return time()

def username():
    return getpwuid(geteuid())[0]

whoami = username

class tee :
    def __init__(self, _fd1, _fd2) :
        self.fd1 = _fd1
        self.fd2 = _fd2

    def __del__(self) :
        if self.fd1 != sys.stdout and self.fd1 != sys.stderr :
            self.fd1.close()
        if self.fd2 != sys.stdout and self.fd2 != sys.stderr :
            self.fd2.close()

    def write(self, text) :
        self.fd1.write(text)
        self.fd2.write(text)

    def flush(self) :
        self.fd1.flush()
        self.fd2.flush()

    def close(self) :
        self.__del__()

def expand(entry):
    " expand $FOO (environment) then ~jane (user) in entry "
    return expanduser(expandvars(entry))
   
def clean_flist(raw_flist,s=False,lc=False):
    if not raw_flist:
        if (s or STRICT):
            raise Exception, "No file argument provided."
        else:
            perror("No file argument provided.")
            err("No file argument provided.")

    if type(raw_flist) != type(list()):
        raw_flist = raw_flist.strip()
        raw_flist = [raw_flist]

    full_flist = []
    clean_list = []

    for f in raw_flist:
        full_flist.extend(glob(expand(f)))

    for entry in full_flist:
        entry = i3(entry)
        valid = validate_path(entry)
        if exists(entry) and valid:
            clean_list.append(entry)
        elif not valid:
            warning("Invalid path: [%s] - skipping" % entry)
        else:
            warning("[%s] does not exist - skipping" % entry)

    if not clean_list:
        if (s or STRICT):
            raise Exception,"No such file or directory: %s" % raw_flist 
        else:
            warn("No such file or directory: [%s]" % raw_flist)

    return clean_list

def validate_path(path, isfn=False, lc=False):
    #FIXME
    if (lc or LIMITCHARS):
        chars = LIMIT_FILE_CHARS
    else:
        chars = FILE_CHARS

    if not isfn:
        chars+="/"

    if re.match("^[%s]+$" %chars, path) != None:
        return True
    else:
        return False

def pdebug(msg):
    if os.environ.has_key('PYLOG') and os.environ['PYLOG'] in LOG_DEBUG_SET:
        sys.stderr.write("DEBUG: %s\n" % msg)

def pinfo(msg):
    if os.environ.has_key('PYLOG') and os.environ['PYLOG'] in LOG_INFO_SET:
        sys.stderr.write("INFO: %s\n" % msg)

def pwarn(msg):
    if os.environ.has_key('PYLOG') and os.environ['PYLOG'] in LOG_WARN_SET:
        sys.stderr.write("WARN: %s\n" % msg)

def perror(msg):
    if os.environ.has_key('PYLOG') and os.environ['PYLOG'] in LOG_ERROR_SET:
        sys.stderr.write("ERROR: %s\n" % msg)

def pcritical(msg):
    if os.environ.has_key('PYLOG') and os.environ['PYLOG'] in LOG_CRITICAL_SET:
        sys.stderr.write("CRITICAL: %s\n" % msg)

