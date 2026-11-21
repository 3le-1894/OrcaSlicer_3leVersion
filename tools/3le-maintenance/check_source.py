"""Read-only clean committed-source/cache gate. Build/deploy fail closed until integration is committed."""
from pathlib import Path
import hashlib,json,subprocess,sys

def require(ok,message):
 if not ok:raise RuntimeError(message)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(root,policy,git=None):
 root=Path(root)
 if git is None:
  def git(*args):return subprocess.check_output(['git','--no-optional-locks','-C',str(root),*args],stderr=subprocess.DEVNULL).decode()
 require(root.resolve()==Path(policy['source']).resolve(),'Wrong source path')
 require(git('rev-parse','--show-toplevel').strip()==str(root.resolve()),'Wrong repository root')
 require(git('branch','--show-current').strip()==policy['branch'],'Wrong branch')
 git('merge-base','--is-ancestor',policy['base'],'HEAD')
 require(not git('status','--porcelain','--untracked-files=all').strip(),'Source is dirty/uncommitted; review and commit first')
 tracked=set(git('ls-files','-z').split('\0'))
 for n in policy['required_tracked']:require(n in tracked,'Required integration file is not committed: '+n)
 for n,h in policy['files'].items():
  p=root/n;require(p.is_file() and not p.is_symlink() and digest(p)==h,'Reviewed source/package identity changed: '+n)
 return git('rev-parse','HEAD').strip()
def check_cache(root,prefix,dependencies=None):
 root=Path(root);prefix=Path(prefix)
 require(prefix.is_dir(),'Dependency prefix missing')
 require((prefix/'libpython/lib/libpython3.12.so').is_file(),'Bundled Python dependency missing')
 if dependencies is not None:
  for n,h in dependencies.items():require((prefix/n).is_file() and digest(prefix/n)==h,'Dependency prefix changed: '+n)
 build=root/'build';cache=build/'CMakeCache.txt'
 if not build.exists():return
 require(cache.is_file(),'Existing build directory has no approved CMake cache; retain and inspect')
 values={}
 for line in cache.read_text().splitlines():
  if '=' in line and not line.startswith(('#','//')):
   k,v=line.split('=',1);values[k.split(':')[0]]=v
 for k,v in {'CMAKE_HOME_DIRECTORY':str(root.resolve()),'CMAKE_PREFIX_PATH':str(prefix),'CMAKE_GENERATOR':'Ninja Multi-Config','CMAKE_CXX_COMPILER':'/usr/bin/c++'}.items():require(values.get(k)==v,'Incompatible native cache: '+k)
 require(values.get('Python3_ROOT_DIR')==str(prefix/'libpython'),'Incompatible Python prefix')
 require(values.get('FETCHCONTENT_FULLY_DISCONNECTED')=='ON','Cache permits dependency fetching')
if __name__=='__main__':
 try:
  root=Path(__file__).resolve().parents[2];policy=json.loads((Path(__file__).parent/'policy.json').read_text())
  from run_contract import tools
  tools(policy)
  head=check(root,policy);check_cache(root,policy['dependency_prefix'],json.loads((Path(__file__).parent/'dependency-hashes.json').read_text()));print('PASS committed integration source/cache at '+head)
 except (RuntimeError,OSError,subprocess.CalledProcessError) as e:raise SystemExit('STOP: '+str(e))
