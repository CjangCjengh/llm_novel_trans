import os
import hashlib
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI


cache_dir = 'cache'
os.makedirs(cache_dir, exist_ok=True)

os.environ['OPENAI_API_KEY'] = '<your api key here>'
os.environ['OPENAI_API_BASE'] = '<your api base here>'
llm = ChatOpenAI(model_name='DeepSeek-R1-671B')

def stream_generate(prompt: str) -> str:
    md5_cache = calculate_md5(prompt)
    cache_path = f'{cache_dir}/{md5_cache}.txt'
    if os.path.exists(cache_path):
        with open(cache_path,'r',encoding='utf-8') as f:
            return f.read()
    messages = [HumanMessage(content=prompt)]
    full_response = ''
    for chunk in llm.stream(messages):
        content_chunk = chunk.content
        print(content_chunk, end='', flush=True)
        full_response += content_chunk
    print()
    with open(cache_path,'w',encoding='utf-8') as f:
        f.write(full_response)
    return full_response

def calculate_md5(input_string):
    md5_object = hashlib.md5()
    md5_object.update(input_string.encode('utf-8'))
    md5_hash = md5_object.hexdigest()
    return md5_hash
