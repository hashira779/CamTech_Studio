import urllib.request
import json

req_data = json.dumps({'audio_path': 'uploads/audio/tBu4Qq5fSiU.mp3'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/transcribe', data=req_data, headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode('utf-8'))

print('Status:', data.get('status'))
print('Source:', data.get('source'))
print('File:', data.get('file'))
print('Lines count:', len(data.get('lyrics', [])))

lyrics = data.get('lyrics', [])
if lyrics:
    print('\nFirst 3 lines:')
    for l in lyrics[:3]:
        s = l['start']
        e = l['end']
        t = l['text']
        print(f'[{s:05.2f} -> {e:05.2f}] {t}')
        words_summary = ' | '.join([f"{w['word']} ({w['start']}s-{w['end']}s)" for w in l.get('words', [])[:5]])
        print(f'   Words: {words_summary} ...')
