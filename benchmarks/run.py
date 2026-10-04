#!/usr/bin/env python3
import argparse,csv,datetime as dt,json,pathlib,subprocess,threading,time,urllib.request,urllib.error,hashlib
# Sanitised public adaptation: paths/endpoints parameterised; process/Docker snapshots removed.
P=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--run',required=True,choices=['warmup','run-01','run-02','run-03'])
parser.add_argument('--endpoint',default='http://127.0.0.1:8097/completion')
parser.add_argument('--request',type=pathlib.Path,default=P/'request.json')
parser.add_argument('--output-dir',type=pathlib.Path,required=True)
args=parser.parse_args()
base=args.output_dir.resolve()
if base==P or P in base.parents: raise SystemExit('use an output directory outside benchmarks/')
base.mkdir(parents=True,exist_ok=True)
prefix=base/args.run
outputs={k:pathlib.Path(str(prefix)+suffix) for k,suffix in {'response':'.response.json','client':'.client.json','gpu':'.gpu.csv','host':'.host.csv'}.items()}
for path in outputs.values():
    if path.exists(): raise SystemExit(f'refusing existing file: {path}')
request_file=args.request
body=request_file.read_bytes()
stop=threading.Event(); gpu=[]; host=[]
def sample():
    prev=None
    while not stop.is_set():
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        p=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.used,utilization.gpu,power.draw,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15)
        for row in csv.reader(p.stdout.splitlines()):
            if len(row)==6: gpu.append([stamp]+[x.strip() for x in row])
        cpu=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
        total=sum(cpu[:8]); idle=cpu[3]+cpu[4]
        pct=None if prev is None or total==prev[0] else 100*(1-(idle-prev[1])/(total-prev[0]))
        prev=(total,idle)
        mem={}
        for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
            k,v=line.split(':',1); mem[k]=int(v.strip().split()[0])
        host.append([stamp,pct,mem['MemTotal'],mem['MemAvailable'],mem['SwapTotal']-mem['SwapFree']])
        stop.wait(0.5)
thread=threading.Thread(target=sample,daemon=True);thread.start()
req=urllib.request.Request(args.endpoint,data=body,headers={'Content-Type':'application/json'},method='POST')
started=dt.datetime.now(dt.timezone.utc).isoformat();t=time.perf_counter()
try:
    with urllib.request.urlopen(req,timeout=240) as response:
        status=response.status;raw=response.read()
except urllib.error.HTTPError as error:
    status=error.code;raw=error.read()
except Exception as error:
    status=None;raw=json.dumps({'client_error':type(error).__name__,'detail':str(error)}).encode()
elapsed=time.perf_counter()-t
stop.set();thread.join(timeout=20)
outputs['response'].write_bytes(raw+b'\n')
for key,header,rows in [('gpu',['timestamp_utc','index','name','memory_used_mib','gpu_util_percent','power_w','temperature_c'],gpu),('host',['timestamp_utc','cpu_busy_percent','mem_total_kib','mem_available_kib','swap_used_kib'],host)]:
    with outputs[key].open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(header);writer.writerows(rows)
client={'run':args.run,'started_utc':started,'elapsed_seconds':elapsed,'http_status':status,'request_sha256':hashlib.sha256(body).hexdigest(),'endpoint':args.endpoint,'stream':False,'ttft_seconds':None,'ttft_reason':'not measurable by this nonstreaming client','gpu_samples':len(gpu),'host_samples':len(host)}
outputs['client'].write_text(json.dumps(client,indent=2)+'\n')
result=json.loads(raw)
print(json.dumps({'run':args.run,'status':status,'client_elapsed_s':elapsed,'content_preview':result.get('content','')[:100],'tokens_predicted':result.get('tokens_predicted'),'timings':result.get('timings')}),flush=True)
assert status==200 and result.get('content') and result.get('timings',{}).get('predicted_per_second',0)>0,'invalid inference result'
assert result.get('tokens_predicted')==256,'benchmark did not generate 256 tokens'
assert result.get('timings',{}).get('cache_n')==0,'unexpected prompt reuse'
