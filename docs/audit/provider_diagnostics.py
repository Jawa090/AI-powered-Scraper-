"""Sanitized live provider errors; never prints API keys or DSNs."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from agents.llm.chat_model import ProviderChain,_build_model,_classify_error
from langchain_core.messages import HumanMessage
from utils.pii import mask_payload
for name,provider,model,key,base in ProviderChain()._candidates():
    if not key: continue
    try:
        instance=_build_model(provider=provider,model=model,api_key=key,base_url=base,timeout=12)
        response=instance.invoke([HumanMessage(content='Reply OK.')])
        print(json.dumps({'provider':name,'model':model,'reachable':True}),flush=True)
    except Exception as exc:
        print(json.dumps(mask_payload({'provider':name,'model':model,'reachable':False,'type':type(exc).__name__,
            'reason':_classify_error(exc)[0],'message':str(exc)[:700]})),flush=True)
