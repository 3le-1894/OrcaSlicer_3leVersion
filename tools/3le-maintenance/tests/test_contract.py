"""Synthetic source/cache state tests; no commits, compiler, GUI or updater invocation."""
from pathlib import Path
import importlib.util,hashlib,json,tempfile,unittest,subprocess
M=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_gate',M/'check_source.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class Contract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'accepted.cpp').write_text('accepted source\n')
  self.policy={'source':str(self.root),'branch':'maintenance/test','base':'base','required_tracked':['accepted.cpp'],'files':{'accepted.cpp':gate.digest(self.root/'accepted.cpp')}}
  self.state={'branch':'maintenance/test','dirty':'','tracked':'accepted.cpp\0','ancestor':True}
 def git(self,*args):
  if args==('rev-parse','--show-toplevel'):return str(self.root)
  if args==('rev-parse','HEAD'):return 'later-reviewed-commit'
  if args==('branch','--show-current'):return self.state['branch']
  if args[0]=='merge-base':
   if not self.state['ancestor']:raise subprocess.CalledProcessError(1,args)
   return ''
  if args[0]=='status':return self.state['dirty']
  if args[0]=='ls-files':return self.state['tracked']
  raise AssertionError(args)
 def test_clean_committed_descendant(self):self.assertEqual(gate.check(self.root,self.policy,self.git),'later-reviewed-commit')
 def test_wrong_path(self):
  self.policy['source']='/unexpected'
  with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
 def test_wrong_branch(self):
  self.state['branch']='old-held-branch'
  with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
 def test_wrong_ancestry(self):
  self.state['ancestor']=False
  with self.assertRaises(subprocess.CalledProcessError):gate.check(self.root,self.policy,self.git)
 def test_dirty_and_untracked(self):
  for dirty in (' M accepted.cpp','M  accepted.cpp','?? held.cpp'):
   self.state['dirty']=dirty
   with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
 def test_uncommitted_required_file(self):
  self.state['tracked']=''
  with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
 def test_missing_or_changed_accepted_code(self):
  (self.root/'accepted.cpp').write_text('missing readiness\n')
  with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
  (self.root/'accepted.cpp').unlink()
  with self.assertRaises(RuntimeError):gate.check(self.root,self.policy,self.git)
 def test_cache_mapping(self):
  prefix=self.root/'deps';(prefix/'libpython/lib').mkdir(parents=True);(prefix/'libpython/lib/libpython3.12.so').touch()
  gate.check_cache(self.root,prefix) # No existing native objects to reuse.
  build=self.root/'build';build.mkdir()
  with self.assertRaises(RuntimeError):gate.check_cache(self.root,prefix)
  values={'CMAKE_HOME_DIRECTORY':str(self.root),'CMAKE_PREFIX_PATH':str(prefix),'CMAKE_GENERATOR':'Ninja Multi-Config','CMAKE_CXX_COMPILER':'/usr/bin/c++','Python3_ROOT_DIR':str(prefix/'libpython'),'FETCHCONTENT_FULLY_DISCONNECTED':'ON'}
  def save(): (build/'CMakeCache.txt').write_text(''.join(k+':STRING='+v+'\n' for k,v in values.items()))
  save();gate.check_cache(self.root,prefix)
  for key in values:
   old=values[key];values[key]='incompatible';save()
   with self.assertRaises(RuntimeError):gate.check_cache(self.root,prefix)
   values[key]=old
if __name__=='__main__':unittest.main()
