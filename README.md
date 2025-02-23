# Translation Tool

This tool is designed to translate novels and save the results and terms used in the translation process.

## API Configuration

Open `stream_api.py`.
Enter your API Key and API Base on lines 10 and 11:

```python
API_KEY = 'your_api_key_here'
API_BASE = 'your_api_base_here'
```

Specify the model on line 12:

```python
llm = ChatOpenAI(model_name='your_model_here')
```

## Translation Execution 

Open `translator.py`.
On line 248:

```python
translator.translate('vi.txt', 'zh.json', 'terms.json')
```

This command translates the contents of `vi.txt` and saves it to `zh.json`. During the translation process, it will also generate a terms glossary, which will be saved to `terms.json`.

```bash
python translator.py
```

After executing the script, you will find the translated content in `zh.json` and any utilized terms in `terms.json`.

Additionally, it supports a resume translation feature, allowing you to continue from where you left off in case of interruptions.
