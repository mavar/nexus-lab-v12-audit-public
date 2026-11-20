"""Cache the locked Next.js archive using bounded HTTP Range requests."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
CHUNK = 1024*1024


def request(url, begin, end):
    req = urllib.request.Request(url,headers={'Range':f'bytes={begin}-{end}'})
    last_error = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                data = response.read()
                header = response.headers.get('Content-Range','')
                if response.status!=206 or not header.startswith(f'bytes {begin}-{end}/') or len(data)!=end-begin+1:
                    raise ValueError('Registry did not return the requested archive range.')
                return data,header
        except (OSError,ValueError) as error:
            last_error = error
    raise RuntimeError(f'Cannot fetch archive bytes {begin}-{end}') from last_error


def main():
    package = json.loads((HERE/'web/package-lock.json').read_text())['packages']['node_modules/next']
    url = package['resolved']
    if not url.startswith('https://registry.npmjs.org/next/-/'):
        raise ValueError('Expected the official locked Next.js archive.')
    first,header = request(url,0,CHUNK-1)
    match = re.fullmatch(r'bytes 0-1048575/(\d+)',header)
    if not match:
        raise ValueError('Unknown archive size.')
    total = int(match[1])
    if not CHUNK <= total <= 200*CHUNK:
        raise ValueError('Unexpected archive size.')
    ranges = [(begin,min(total-1,begin+CHUNK-1)) for begin in range(CHUNK,total,CHUNK)]
    output = HERE/'artifacts/next-locked.tgz'
    output.parent.mkdir(exist_ok=True)
    digest = hashlib.sha512()
    with output.open('wb') as file:
        file.write(first)
        digest.update(first)
        with ThreadPoolExecutor(max_workers=4) as executor:
            for i, data in enumerate(executor.map(lambda pair: request(url,*pair)[0],ranges),start=2):
                file.write(data)
                digest.update(data)
                if i%8==0 or i==len(ranges)+1:
                    print(f'Next.js archive: {min(i*CHUNK,total)}/{total} bytes',flush=True)
    expected = package['integrity']
    if expected!='sha512-'+base64.b64encode(digest.digest()).decode():
        raise ValueError('Archive checksum differs from package-lock.json. Do not use it.')
    npm = ['cmd','/d','/c','npm.cmd'] if os.name=='nt' else ['npm']
    subprocess.run([*npm,'cache','add',str(output)],cwd=HERE/'web',check=True,timeout=60)
    print('Official Next.js archive verified and added to npm cache.')


if __name__=='__main__':
    main()
