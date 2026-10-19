"""Run the downloaded tool in a separate process, confined to its output writes."""
import os
from pathlib import Path
import re
import sys


def main():
    engine,source,config,output=sys.argv[1:]
    sys.dont_write_bytecode=True
    sys.path[:0]=[engine,str(Path(engine)/'filetype-1.2.0-py2.py3-none-any.whl')]
    from Core.lpk_loader import LpkLoader
    root=Path(output).resolve()
    def checked(value):
        if isinstance(value,(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(value)).resolve()
            if path!=root and not path.is_relative_to(root):
                raise ValueError('LPK attempted to write outside its output directory')
    def audit(event,args):
        if event=='open':
            mode=args[1];flags=args[2]
            if (isinstance(mode,str) and any(char in mode for char in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                checked(args[0])
        elif event in ('os.mkdir','os.remove','os.rmdir'):checked(args[0])
        elif event in ('os.rename','os.link','os.symlink'):
            checked(args[0]);checked(args[1])
        elif event=='shutil.copyfile':checked(args[1])
    sys.addaudithook(audit)
    LpkLoader.name_change=lambda self,name:re.sub(r'[\\/<>:"|?*\x00-\x1f]','_',str(name).replace('FileReferences_',''))[:180]
    loader=LpkLoader(source,config or None)
    loader.extract(str(root))


if __name__=='__main__':main()
