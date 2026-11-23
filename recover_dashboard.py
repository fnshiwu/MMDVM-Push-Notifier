#!/usr/bin/env python3
# MMDVM-Push-Notifier HTTP 500 recovery — idempotent, makes backups, php -l verified
import io, os, re, shutil, subprocess, time
CAND = ["/var/www/dashboard/admin/index.php","/var/www/dashboard/index.php","/var/www/html/index.php","/var/www/index.php"]
LINK = '<a href="/admin/push_admin.php" style="color: #ffffff;">\u63a8\u9001\u8bbe\u7f6e</a> | '
ECHO = 'echo \' ' + LINK + '\'."\\n";'
ANCHOR = re.compile(r'<a\s+href=["\']/admin/(?:update|power|configure)\.php["\']')
def lint(p):
    try:
        r=subprocess.run(["php","-l",p],capture_output=True,text=True,timeout=20)
        return r.returncode==0,(r.stdout or r.stderr).strip()
    except Exception as e:
        return False,str(e)
def strip(src):
    """Remove our injected link and repair any splice damage to menu lines."""
    out=[]
    for ln in src.splitlines(True):
        if "push_admin.php" in ln:
            st=ln.lstrip()
            # Our injected echo (valid or spliced into a string literal) and
            # the raw-HTML variant both belong to us: drop them entirely.
            if (st.startswith("echo ") or st.startswith('<a href="/admin/push_admin.php"')
                    or "echo ' echo '" in ln):
                continue
        # Splice damage: the ORIGINAL menu line lost its `echo ' ` prefix when
        # our echo (which carried that prefix) was removed. Such a line is a
        # bare `<a href="/admin/...>'."\n";` fragment. Restore the prefix.
        st=ln.lstrip()
        # A genuine original menu echo always ends with the PHP tail `'."\n";`.
        # A plain HTML link (e.g. configure.php) does not. Only repair the former.
        if (re.match(r'<a\s+href=["\']/admin/', st)
                and re.search(r'["\']\s*\.\s*"\\n"\s*;\s*$', st)):
            m=re.search(r'<a\s+href=["\']/admin/', ln)
            if m:
                ln=ln[:m.start()]+"echo ' "+ln[m.start():]
        out.append(ln)
    return "".join(out).replace(LINK,"")

def inject(src):
    m=ANCHOR.search(src)
    if not m: return src,False
    pos=m.start(); ls=src.rfind("\n",0,pos)+1; le=src.find("\n",pos)
    al=src[ls: le if le>=0 else len(src)]
    if re.match(r"\s*(echo|print)\b",al):
        ind=re.match(r"\s*",al).group(0); src=src[:ls]+ind+ECHO+"\n"+src[ls:]
    else:
        src=src[:pos]+LINK+src[pos:]
    return src,True
def main():
    stamp=time.strftime("%Y%m%d-%H%M%S"); results=[]
    for p in CAND:
        if not os.path.isfile(p): continue
        try: src=io.open(p,encoding="utf-8",errors="ignore").read()
        except OSError as e: print("SKIP",p,e); continue
        had="push_admin.php" in src
        ok,_=lint(p)
        if had and ok and "echo ' echo '" not in src:
            # one clean link, valid syntax → leave as-is
            print("CLEAN",p,"| php-lint OK"); continue
        # Choose the healthiest base: prefer backup if it parses
        base=src
        bak=p+".bak_pushnav"
        if os.path.isfile(bak):
            try: bs=io.open(bak,encoding="utf-8",errors="ignore").read()
            except OSError: bs=""
            if bs:
                t="/tmp/_lint_"+str(os.getpid()); io.open(t,"w",encoding="utf-8").write(bs)
                if lint(t)[0]: base=bs
        new=strip(base); new,inj=inject(new)
        shutil.copyfile(p,p+".pre-recover-"+stamp)
        io.open(p,"w",encoding="utf-8").write(new)
        ok,msg=lint(p)
        print("REPAIRED",p,"| injected="+str(inj),"| php-lint:","OK" if ok else msg)
        results.append((p,ok))
    if not results: print("NO_FILES_CHANGED")
    bad=[p for p,o in results if not o]
    print("RESULT:","ALL_OK" if not bad else "STILL_BROKEN: "+", ".join(bad))
if __name__=="__main__":
    main()
