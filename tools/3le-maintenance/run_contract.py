"""Run/package checks and exclusive staged provenance; never invokes a build or service."""
from pathlib import Path
import hashlib,json,os,sys,stat
import check_source as gate

def tools(policy):
 result={}
 for name,item in policy['external_tools'].items():
  p=Path(item['path'])
  gate.require(p.is_file() and not p.is_symlink() and os.access(p,os.X_OK),'Missing/nonexecutable external tool: '+name)
  gate.require(gate.digest(p)==item['sha256'],'External tool changed: '+name)
  result[name]={'path':str(p),'sha256':gate.digest(p),'executable':True}
 return result

def identity(root,policy,git=None):
 root=Path(root);head=gate.check(root,policy,git)
 m=root/'tools/3le-maintenance'
 helpers={str(p.relative_to(root)):gate.digest(p) for p in sorted(m.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
 return {'head':head,'source_directory':str(root),'branch':policy['branch'],'policy_sha256':gate.digest(m/'policy.json'),'maintenance_files':helpers,'external_tools':tools(policy)}

def same(root,policy,saved,git=None):
 gate.require(identity(root,policy,git)==saved,'Build-run revision/policy/helper/tool identity drift')

def inventory(package,policy,*,stage=False):
 package=Path(package)
 gate.require(package.is_dir() and not package.is_symlink(),'Directory runtime output missing')
 for entry in ('orca-slicer','bin/orca-slicer','libexec/orca-slicer-env'):
  p=package/entry;gate.require(p.is_file() and os.access(p,os.X_OK),'Missing/nonexecutable runtime output: '+entry)
 gate.require((package/'resources/profiles').is_dir(),'Runtime profiles missing')
 provenance=package/'build.json'
 if stage:
  gate.require(provenance.is_file() and not provenance.is_symlink(),'Staged provenance must be a regular non-symlink file')
 else:
  gate.require(not os.path.lexists(provenance),'Reserved build.json exists in build output')
 uv=package/'resources/tools/uv/uv'
 gate.require(uv.is_file() and not uv.is_symlink() and os.access(uv,os.X_OK),'Packaged uv missing/nonexecutable')
 gate.require(gate.digest(uv)==policy['external_tools']['uv']['sha256'],'Packaged uv changed')
 entries={}
 for p in sorted(package.rglob('*')):
  n=str(p.relative_to(package))
  if n=='build.json':continue # Allowed only after the explicit stage check above.
  if p.is_symlink():
   gate.require(p.resolve().is_relative_to(package.resolve()) and p.resolve().exists(),'Unsafe package symlink: '+n)
   entries[n]={'link':os.readlink(p)}
  elif p.is_file():entries[n]={'sha256':gate.digest(p),'mode':p.stat().st_mode & 0o777}
  elif p.is_dir():entries[n]={'directory':True}
  else:raise RuntimeError('Unsupported package entry: '+n)
 return entries

def seal(root,policy,saved,package,git=None):
 same(root,policy,saved,git)
 return {'run':saved,'directory_runtime':inventory(package,policy)}

def provenance_value(saved):
 return {'base_commit':saved['head'],'source_directory':saved['source_directory'],'status':'','build_identity':saved}

def write_provenance(root,policy,saved,seal_record,package,git=None):
 # Revalidate fresh staged output BEFORE copying any reserved provenance into it.
 same(root,policy,saved,git)
 gate.require(seal_record['run']==saved,'Package belongs to another build run')
 gate.require(inventory(package,policy)==seal_record['directory_runtime'],'Fresh staged directory runtime drift')
 directory=os.open(package,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  # O_EXCL rejects any existing file/link/dangling link/directory, including a race
  # after inventory(). The directory-relative open never follows build.json.
  fd=os.open('build.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
  with os.fdopen(fd,'w') as f:json.dump(provenance_value(saved),f,indent=2);f.write('\n')
 finally:os.close(directory)

def read_provenance(package):
 directory=os.open(package,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  fd=os.open('build.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
  try:
   gate.require(stat.S_ISREG(os.fstat(fd).st_mode),'Provenance is not a regular file')
   with os.fdopen(fd,'r') as f:
    fd=None
    return json.load(f)
  finally:
   if fd is not None:os.close(fd)
 finally:os.close(directory)

def staged(root,policy,saved,seal_record,package,git=None):
 same(root,policy,saved,git)
 gate.require(seal_record['run']==saved,'Package belongs to another build run')
 gate.require(inventory(package,policy,stage=True)==seal_record['directory_runtime'],'Built/staged directory runtime drift')
 provenance=read_provenance(package)
 gate.require(provenance==provenance_value(saved),'Staged provenance changed')

if __name__=='__main__':
 root=Path(__file__).resolve().parents[2];policy=json.loads((Path(__file__).parent/'policy.json').read_text())
 gate.check_cache(root,policy['dependency_prefix'],json.loads((Path(__file__).parent/'dependency-hashes.json').read_text()))
 cmd=sys.argv[1];saved_path=Path(sys.argv[2])
 if cmd=='capture':
  gate.require(sys.argv[3]==policy['external_tools']['uv']['path'],'Build uv path differs from policy')
  gate.require(not saved_path.exists(),'Run identity already exists')
  saved_path.write_text(json.dumps(identity(root,policy),indent=2)+'\n')
 else:
  saved=json.loads(saved_path.read_text())
  if cmd=='check':same(root,policy,saved)
  elif cmd=='seal':
   result=seal(root,policy,saved,sys.argv[3]);out=Path(sys.argv[4]);gate.require(not out.exists(),'Package seal exists');out.write_text(json.dumps(result,indent=2)+'\n')
  elif cmd=='provenance':
   write_provenance(root,policy,saved,json.loads(Path(sys.argv[3]).read_text()),sys.argv[4])
  elif cmd=='staged':staged(root,policy,saved,json.loads(Path(sys.argv[3]).read_text()),sys.argv[4])
  else:raise SystemExit('Unknown run-contract operation')
 print('PASS run contract '+cmd)
