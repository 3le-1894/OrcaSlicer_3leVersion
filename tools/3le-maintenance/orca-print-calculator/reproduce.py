"""Reconstruct exact reviewed package into NEW_DIRECTORY. No network, native build or installation."""
from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile,io,csv,base64,sys
R=Path(__file__).resolve().parent
D=Path(sys.argv[1]).resolve()
assert not D.exists(),'Destination must not exist'
info=json.loads((R/'PROVENANCE.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
for n,h in info['files'].items():assert sha((R/n).read_bytes())==h,n
D.mkdir();P=D/'source';shutil.copytree(R/'baseline',P)
subprocess.run(['patch','-p1','--fuzz=0','-i',str(R/'plugin.patch')],cwd=P,check=True)
old=P/'orca_print_calculator-0.6.2.dist-info';new=old.with_name('orca_print_calculator-0.6.2+3le.connect.r3.dist-info');old.rename(new)
f=new/'METADATA';f.write_text(f.read_text().replace('Version: 0.6.2\n','Version: 0.6.2+3le.connect.r3\n'))
record=str((new/'RECORD').relative_to(P));entries={str(p.relative_to(P)):p.read_bytes() for p in P.rglob('*') if p.is_file() and p.name!='RECORD'}
buf=io.StringIO();writer=csv.writer(buf,lineterminator='\n')
for n,b in sorted(entries.items()):writer.writerow([n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('='),len(b)])
writer.writerow([record,'','']);entries[record]=buf.getvalue().encode();(P/record).write_bytes(entries[record])
for n,b in entries.items():assert b==(R/'source'/n).read_bytes(),n
with zipfile.ZipFile(D/'orca_print_calculator_any.whl','w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(entries.items()):
  zinfo=zipfile.ZipInfo(n,(1980,1,1,0,0,0));zinfo.compress_type=zipfile.ZIP_DEFLATED;zinfo.external_attr=0o100644<<16;z.writestr(zinfo,b)
assert sha((D/'orca_print_calculator_any.whl').read_bytes())==info['wheel_sha256']
print('PASS exact 0.6.2+3le.connect.r3 package; not installed')
