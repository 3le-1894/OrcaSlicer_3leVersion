from pathlib import Path
import json,sys,os,unittest
M=Path(__file__).resolve().parents[1];sys.path.insert(0,str(M))
import run_contract as run
import test_contract as base
class RunContract(base.Contract):
 def setUp(self):
  super().setUp();self.m=self.root/'tools/3le-maintenance';self.m.mkdir(parents=True)
  (self.m/'policy.json').write_text('{}');self.uv=self.root/'approved-uv';self.uv.write_bytes(b'synthetic tool bytes; NEVER EXECUTE');self.uv.chmod(0o700)
  self.policy['external_tools']={'uv':{'path':str(self.uv),'sha256':run.gate.digest(self.uv)}}
  self.head='later-reviewed-commit'
 def git(self,*args):
  if args==('rev-parse','HEAD'):return self.head
  return super().git(*args)
 def package(self):
  p=self.root/'runtime'
  for n in ('orca-slicer','bin/orca-slicer','libexec/orca-slicer-env','resources/tools/uv/uv'):
   f=p/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(self.uv.read_bytes() if n=='resources/tools/uv/uv' else b'generated');f.chmod(0o700)
  (p/'resources/profiles').mkdir();return p
 def test_clean_descendant_during_build_and_wait(self):
  for boundary in ('build','preactivation-wait'):
   self.head='revision-A';saved=run.identity(self.root,self.policy,self.git);self.head='revision-B'
   with self.assertRaises(RuntimeError,msg=boundary):run.same(self.root,self.policy,saved,self.git)
 def test_policy_helper_and_dirty_drift(self):
  saved=run.identity(self.root,self.policy,self.git)
  (self.m/'policy.json').write_text('{"changed":true}')
  with self.assertRaises(RuntimeError):run.same(self.root,self.policy,saved,self.git)
  (self.m/'policy.json').write_text('{}');(self.m/'new_helper.py').write_text('changed')
  with self.assertRaises(RuntimeError):run.same(self.root,self.policy,saved,self.git)
  (self.m/'new_helper.py').unlink();self.state['dirty']=' M source'
  with self.assertRaises(RuntimeError):run.same(self.root,self.policy,saved,self.git)
 def test_external_uv_missing_changed_nonexecutable(self):
  for failure in ('changed','nonexec','missing'):
   self.uv.write_bytes(b'synthetic tool bytes; NEVER EXECUTE');self.uv.chmod(0o700)
   saved=run.identity(self.root,self.policy,self.git)
   if failure=='changed':self.uv.write_bytes(b'different tool')
   if failure=='nonexec':self.uv.chmod(0o600)
   if failure=='missing':self.uv.unlink()
   with self.assertRaises(RuntimeError):run.same(self.root,self.policy,saved,self.git)
 def test_packaged_uv_missing_changed_nonexecutable(self):
  p=self.package();uv=p/'resources/tools/uv/uv'
  for failure in ('changed','nonexec','missing'):
   uv.write_bytes(self.uv.read_bytes());uv.chmod(0o700)
   if failure=='changed':uv.write_bytes(b'different')
   if failure=='nonexec':uv.chmod(0o600)
   if failure=='missing':uv.unlink()
   with self.assertRaises(RuntimeError):run.inventory(p,self.policy)
 def test_package_seal_and_captured_provenance(self):
  saved=run.identity(self.root,self.policy,self.git);p=self.package();sealed=run.seal(self.root,self.policy,saved,p,self.git)
  run.write_provenance(self.root,self.policy,saved,sealed,p,self.git)
  run.staged(self.root,self.policy,saved,sealed,p,self.git)
  record=json.loads((p/'build.json').read_text());record['base_commit']='later-revision-B';(p/'build.json').write_text(json.dumps(record))
  with self.assertRaises(RuntimeError):run.staged(self.root,self.policy,saved,sealed,p,self.git)
  record['base_commit']=saved['head'];(p/'build.json').write_text(json.dumps(record))
  (p/'bin/orca-slicer').write_bytes(b'staged artifact changed')
  with self.assertRaises(RuntimeError):run.staged(self.root,self.policy,saved,sealed,p,self.git)

 def test_actual_uv_layout_positive_and_flat_rejection(self):
  p=self.package();self.assertIn('resources/tools/uv/uv',run.inventory(p,self.policy))
  tool=p/'resources/tools/uv/uv';tool.unlink();tool.parent.rmdir()
  (p/'resources/tools/uv').write_bytes(self.uv.read_bytes());(p/'resources/tools/uv').chmod(0o700)
  with self.assertRaises(RuntimeError):run.inventory(p,self.policy)

 def test_reserved_provenance_rejected_without_writes(self):
  p=self.package();saved=run.identity(self.root,self.policy,self.git);sealed=run.seal(self.root,self.policy,saved,p,self.git)
  outside=self.root/'outside';outside.write_text('outside sentinel')
  inside=p/'bin/orca-slicer';inside_bytes=inside.read_bytes()
  reserved=p/'build.json'
  for kind in ('external-link','internal-link','dangling-link','root-link','existing-file','directory'):
   if kind=='external-link':reserved.symlink_to(outside)
   if kind=='internal-link':reserved.symlink_to(inside)
   if kind=='dangling-link':reserved.symlink_to(self.root/'does-not-exist')
   if kind=='root-link':reserved.symlink_to(p, target_is_directory=True)
   if kind=='existing-file':reserved.write_text('{}')
   if kind=='directory':reserved.mkdir()
   with self.assertRaises(RuntimeError,msg=kind):run.seal(self.root,self.policy,saved,p,self.git)
   with self.assertRaises(RuntimeError,msg=kind):run.write_provenance(self.root,self.policy,saved,sealed,p,self.git)
   with self.assertRaises((RuntimeError,OSError),msg=kind):run.staged(self.root,self.policy,saved,sealed,p,self.git)
   self.assertEqual(outside.read_text(),'outside sentinel');self.assertEqual(inside.read_bytes(),inside_bytes)
   self.assertFalse((self.root/'does-not-exist').exists())
   if kind=='existing-file':self.assertEqual(reserved.read_text(),'{}')
   if reserved.is_symlink() or reserved.is_file():reserved.unlink()
   else:reserved.rmdir()
  run.write_provenance(self.root,self.policy,saved,sealed,p,self.git)
  self.assertFalse(reserved.is_symlink());self.assertTrue(reserved.is_file())
  run.staged(self.root,self.policy,saved,sealed,p,self.git)
  with self.assertRaises(RuntimeError):run.inventory(p,self.policy) # Stage-only allowance is explicit.
  with self.assertRaises(RuntimeError):run.write_provenance(self.root,self.policy,saved,sealed,p,self.git)

 def test_package_root_link_rejected(self):
  p=self.package();linked=self.root/'package-link';linked.symlink_to(p,target_is_directory=True)
  saved=run.identity(self.root,self.policy,self.git);sealed=run.seal(self.root,self.policy,saved,p,self.git)
  with self.assertRaises(RuntimeError):run.write_provenance(self.root,self.policy,saved,sealed,linked,self.git)
  self.assertFalse((p/'build.json').exists())

 def test_exclusive_create_blocks_reserved_link_race(self):
  # Exercise the actual exclusive open after the preflight inventory has passed.
  from unittest.mock import patch
  p=self.package();saved=run.identity(self.root,self.policy,self.git);sealed=run.seal(self.root,self.policy,saved,p,self.git)
  outside=self.root/'race-outside';outside.write_text('unchanged sentinel')
  real=run.inventory
  def raced(*args,**kwargs):
   result=real(*args,**kwargs);(p/'build.json').symlink_to(outside);return result
  with patch.object(run,'inventory',side_effect=raced):
   with self.assertRaises(FileExistsError):run.write_provenance(self.root,self.policy,saved,sealed,p,self.git)
  self.assertEqual(outside.read_text(),'unchanged sentinel')
