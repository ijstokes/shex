import  shex as s

import  xconfig, xconfig.advanced

class TicToc:
    
    def __init__(self):
        self.start  = 0
        self.stop   = 0
        self.rel    = True
        
    def  tic(self):
        self.start  = s.now()
    
    def toc(self):
        self.stop   = s.now()

class SysInfo:
    
    def __init__(self):
        self.xcfg = xconfig.advanced.AdvancedConfig()
        self.static()
        
    def static(self):
        setattr(self.xcfg, "user",      s.getoutput("whoami"))
        setattr(self.xcfg, "hostname",  s.gethostname())
        setattr(self.xcfg, "pwd",       s.pwd())
        setattr(self.xcfg, "pid",       s.getpid())
        
        setattr(self.xcfg, "uname",     str(s.uname()))
        setattr(self.xcfg, "uptime",    s.getoutput("uptime"))
        setattr(self.xcfg, "cpuinfo",   s.getoutput("cat /proc/cpuinfo"))
    
    def dynamic(self):
        pass
        
    def update(self):
        self.dynamic()

    def entry(self):
        setattr(self.xcfg, "env",           s.environ)

        setattr(self.xcfg, "start_time",    str(s.time()))
        setattr(self.xcfg, "start_htime",   s.asctime(s.gmtime()))
        setattr(self.xcfg, "start_load",    str(s.getloadavg()))
        setattr(self.xcfg, "initial_dir",   s.getoutput("ls -Fla"))
        setattr(self.xcfg, "top",           s.getoutput("top -b -n 1"))
        setattr(self.xcfg, "disk",          s.getoutput("df -k"))
    
    def exit(self):
        setattr(self.xcfg, "stop_time",     str(s.time()))
        setattr(self.xcfg, "stop_htime",    s.asctime(s.gmtime()))
        setattr(self.xcfg, "stop_load",     str(s.getloadavg()))
        setattr(self.xcfg, "proc_time",     str(s.times()))

if __name__ == "__main__":
    si = SysInfo()
    tt = TicToc()
    tt.tic()
    tt.toc()