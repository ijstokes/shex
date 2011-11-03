
# $Id: shextest.py 376 2009-12-01 21:41:05Z jahl $

import unittest
import shex
import os
import os.path
import logging
import shutil

logging.basicConfig(level=logging.DEBUG)

# TODO: write tests for gunzip,
# tar, bzip, untar, bz2, chown, findFile, touch,
# expand, clean_flist, validate_path, pdebug, pinfo, pwarn,
# perror, pcritical 

class BasicShexTest(unittest.TestCase):
    def test_pushd(self):
        #Function pushd
        #Function popd
        dp1 = os.getcwd().split('/')
        shex.pushd("..")
        assert(shex.peek().split('/')==dp1)
        dp2 = os.getcwd().split('/')
        shex.popd()
        dp3 = os.getcwd().split('/')
        assert(dp1==dp3)
        assert(dp2==dp1[:-1])
    def test_ls(self):
        #Function ls
        list = shex.ls("../*")
        list.sort()
        logging.debug("shex ls: %s" %list)
        raw_list = os.listdir("..")
        cmp_list = []
        for item in raw_list:
            if item[0] != ".":
                cmp_list.append("../%s" %item)
        cmp_list.sort()
        logging.debug(cmp_list)
        assert(list==cmp_list)
    def test_rm(self):
        #Function rm
        pre = os.listdir(".")
        fh = open("testrm","w")
        fh.close()
        shex.rm("testrm")
        assert(os.listdir(".")==pre)

    def test_mkdir(self):
        #Function mkdir
        list = os.listdir(".")
        list.append("test")
        list.sort()
        shex.mkdir("test")
        list2 = os.listdir(".")
        list2.sort()
        assert(list==list2)
        os.rmdir("test")
    def test_cp(self):
        #Function cp
        shex.cp("testfile","testfilecopy")
        fh1 = open("testfilecopy","r")
        fh2 = open("testfile","r")
        assert(fh1.readlines()==fh2.readlines())
        fh1.close()
        fh2.close()
        os.remove("testfilecopy")
    def test_cmp_copy(self):
        #Function cmp_copy
        shex.mkdir("testdirec")
        shex.cmp_copy("testfile", "testdirec/testfilecopy")
        fh1 = open("testdirec/testfilecopy", "r")
        fh2 = open("testfile", "r")
        assert(fh1.readlines()==fh2.readlines())
        fh1.close()
        fh2.close()
        os.remove("testdirec/testfilecopy")
        os.rmdir("testdirec")
    def test_cat(self):
        #Function cat
        fh = open("testfile","r")
        assert(shex.cat("testfile")==fh.readlines())
        fh.close()
    def test_sort(self):
        #Function sort
        lines = open("testfile","r").readlines()
        lines.sort()
        sorted = shex.sort("testfile")
        lines.sort()
        logging.debug("sort: %s" %sorted)
        logging.debug(lines)
        assert(lines==sorted)
    def test_curl(self):
        #Function curl
        url = "http://sbgrid.org/grid_amd.jpg"
        shex.curl(url) 
        shex.rm("grid_amd.jpg")
    def test_chmod(self):
        #Function chmod
        old_mode = os.stat("testfile").st_mode % 8**3
        shex.chmod("a+x","testfile")
        new_mode = os.stat("testfile").st_mode % 8**3
        assert(new_mode==(old_mode | 73))
        shex.chmod("a-x","testfile")
        assert(old_mode==os.stat("testfile").st_mode % 8**3)
    def test_head(self):
        #Function head
        numlines = 3
        headlist = shex.head("testfile",numlines)
        fh = open("testfile","r")
        headread = fh.readlines()[:numlines]
        fh.close()
        assert(headlist==headread)
    def test_tail(self):
        #Function tail
        numlines = 3
        taillist = shex.tail("testfile",numlines)
        fh = open("testfile","r")
        tailread = fh.readlines()[-1*numlines:]
        fh.close()
        logging.debug("tail: %s %s" %(taillist,tailread))
        assert(taillist==tailread)
    def test_grep(self):
        #Function grep
        lines = shex.grep("e+","testfile")
        assert(lines==['testfile\n', 'lines\n', 'hello world\n'])
    def test_c(self):
        list = shex.c("ls")
        assert(list==os.listdir("."))
    def test_rmpat(self):
        #Function rm_pat
        pat  = "pat"
        list = os.listdir(".")
        for i in range(1,5):
            fh = open("%s%d" %(pat,i), "w")
            fh.close()
        shex.rm_pat("%s*" %pat)
        assert (os.listdir(".")==list)
    def test_fsplit(self):
        #Function fsplit
        fh = open("testfile", "r")
        a = shex.fsplit("testfile", 1)
        assert(a==['000', '001', '002', '003'])
        fh.close()
        

class BadShexTest(unittest.TestCase):
    def bad_ls(self):
        list = shex.ls("bad/dir/*")
        assert(not list)
    def bad_rm(self):
        list = os.listdir(".")
        shex.rm("badfile")
        assert(os.listdir(".")==list)
    def bad_mkdir(self):
        os.makedirs("test/test2")
        shex.mkdir("test")
        logging.debug("mkdir %s" %os.listdir("test"))
        assert(os.listdir("test")==["test2"])
        os.rmdir("test/test2")
        os.rmdir("test")
    def bad_pushd(self):
        path = os.getcwd()
        shex.pushd("bad/dir")
        assert(path==os.getcwd())
    def bad_cp(self):
        fh = open("file2","w")
        fh.close()
        list = os.listdir(".")
        shex.cp(["testfile","file2"],"file")
        assert(os.listdir(".")==list)
        os.remove("file2")
    def bad_cmp_copy(self):
        fh = open("filex", "w")
        fh.close()
        list = os.listdir(".")
        shex.cmp_copy("testfile", "filex")
        os.remove("filex")
    def bad_curl(self):
        url = "http://sbgrid.org/asdfsaf"
        shex.curl(url)
    def bad_chmod(self):
        mode = os.stat("testfile").st_mode
        shex.chmod("g+q","testfile")
        assert(os.stat("testfile").st_mode==mode)
    def bad_c(self):
        lines = shex.c("la")
        assert('command not found' in lines[0])
    def bad_fsplit(self):
        fh = open("asdf", "r")
        a = shex.fsplit("testfile", 0)
        assert(a==['001', '002', '003', '004'])
        fh.close()
def suite():
    suite1 = unittest.makeSuite(BasicShexTest,'test')
    suite2 = unittest.makeSuite(BadShexTest,'bad')
    allsuites = unittest.TestSuite((suite1,suite2))
    return allsuites

os.makedirs("shex-test")
os.chdir("shex-test")
fh = open("testfile","w")
lines = ["testfile\n","lines\n","hello world\n","abcd\n"]
fh.writelines(lines)
fh.close()
runner = unittest.TextTestRunner()
runner.run(suite())
os.remove("testfile")
os.chdir("..")
shutil.rmtree("shex-test")
