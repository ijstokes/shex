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
