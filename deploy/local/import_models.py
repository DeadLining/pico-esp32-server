#!/usr/bin/env python3
"""Import the current Mac model configuration into the dedicated Pico manager DB.
Does not switch/restart the voice server. Never prints model credentials.
Run with the existing Pico Python environment (PyYAML required).
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['docker', 'compose', '--env-file', str(ROOT/'.runtime/manager.env'), '-f', str(ROOT/'deploy/local/compose.yaml')]

def merge(a, b):
    result = deepcopy(a)
    for key, value in b.items():
        result[key] = merge(result[key], value) if isinstance(value,dict) and isinstance(result.get(key),dict) else deepcopy(value)
    return result

def sql_text(value):
    return 'CONVERT(0x' + str(value).encode('utf-8').hex() + ' USING utf8mb4)' if str(value) else "''"

def make_import(config):
    selected = config['selected_module']
    desired = [('LLM','LLM_PicoGateway','PicoGateway'), ('ASR','ASR_FunASRServer','FunASRServer'), ('TTS','TTS_PaddleSpeechTTS','PaddleSpeechTTS')]
    statements = ['START TRANSACTION;']
    for kind, model_id, code in desired:
        provider = config[kind][selected[kind]]
        expected = {'LLM':'openai','ASR':'fun_server','TTS':'paddle_speech'}[kind]
        if provider.get('type') != expected:
            raise ValueError(f'Unexpected {kind} provider, refusing migration')
        payload = json.dumps(provider,ensure_ascii=False)
        statements.append(f"UPDATE ai_model_config SET is_default=0 WHERE model_type={sql_text(kind)};")
        statements.append('INSERT INTO ai_model_config (id,model_type,model_code,model_name,is_default,is_enabled,config_json,sort,create_date,update_date) VALUES (' + ','.join(map(sql_text,[model_id,kind,code,{'LLM':'Pico 本地网关','ASR':'Pico FunASR（95）','TTS':'Pico PaddleSpeech（95）'}[kind]])) + ',1,1,' + sql_text(payload) + ',0,NOW(),NOW()) ON DUPLICATE KEY UPDATE model_name=VALUES(model_name),is_default=1,is_enabled=1,config_json=VALUES(config_json),update_date=NOW();')
    # Existing templates drive new agents. Existing user-created agents are not modified.
    statements.append("UPDATE ai_agent_template SET asr_model_id='ASR_FunASRServer',llm_model_id='LLM_PicoGateway',tts_model_id='TTS_PaddleSpeechTTS',tts_voice_id='TTS_PaddleSpeechTTS_0000';")
    endpoint = config.get('server',{}).get('websocket')
    if not isinstance(endpoint,str) or not endpoint.startswith(('ws://','wss://')):
        raise ValueError('Missing device WebSocket endpoint')
    for key,value in [('server.websocket',endpoint), ('server.ota','http://82.157.168.149/pico/ota/'), ('server.name','pico-server')]:
        statements.append(f'UPDATE sys_params SET param_value={sql_text(value)} WHERE param_code={sql_text(key)};')
    statements.append('COMMIT;')
    return '\n'.join(statements)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    config=merge(yaml.safe_load((ROOT/'main/pico-server/config.yaml').read_text()),yaml.safe_load((ROOT/'main/pico-server/data/.config.yaml').read_text()))
    sql=make_import(config)
    if not args.apply:
        print('Validated import: PicoGateway, FunASRServer, PaddleSpeechTTS. No database changes; add --apply to import.')
        return
    result=subprocess.run(COMPOSE+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --default-character-set=utf8mb4 -u pico pico_esp32_server'],input=sql,text=True,capture_output=True)
    if result.returncode:
        raise SystemExit('Database import failed. Credentials and SQL were not printed. Voice server unchanged.')
    # Restart only the manager API after import to discard its cached model entries.
    subprocess.run(COMPOSE+['restart','api'],check=True)
    print('Imported three model profiles and updated templates. Voice server has NOT been switched.')

if __name__ == '__main__': main()
