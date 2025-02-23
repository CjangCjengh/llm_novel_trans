from dataclasses import dataclass
from typing import List, Dict, Tuple
import os
import re
import json
from stream_api import stream_generate

@dataclass
class TranslationConfig:
    window_size: int
    context_before: int
    context_after: int
    source_label: str
    target_label: str
    source_lang: str
    target_lang: str

@dataclass
class Term:
    source: str
    target: str
    note: str = ''

class NovelTranslator:
    def __init__(self, config: TranslationConfig):
        self.config = config
        self.terms: Dict[str, Term] = {}
        self.translated_pairs: List[Tuple[str, str]] = []

    def _build_prompt(self, 
                     window: List[str],
                     prev_original: List[str],
                     prev_translated: List[str],
                     next_original: List[str]) -> str:
        prompt_parts = [
            f'将以下内容从{self.config.source_lang}翻译成{self.config.target_lang}，并遵守以下要求：\n'
            '使用中文标点：，。！？：；“”……——（）【】等等\n'
            '翻译时，译文尽量和原文行数相等。\n'
            '如果遇到需要翻译时保持一致且不在术语表中的新术语，比如人名地名专名等，则将其一并输出。\n'
        ]

        current_terms = self._find_terms_in_text(window)
        if current_terms:
            prompt_parts.append('\n## 术语表')
            for term in current_terms:
                prompt_parts.append(f'{term.source} -> {term.target}')

        if prev_original and prev_translated:
            prompt_parts.append('\n## 前文（仅供参考，不用翻译）\n```')
            for orig, trans in zip(prev_original, prev_translated):
                prompt_parts.append(orig)
                prompt_parts.append(trans)
            prompt_parts.append('```')

        prompt_parts.append('\n## 待翻译内容\n```')
        prompt_parts.extend(window)
        prompt_parts.append('```')

        if next_original:
            prompt_parts.append('\n## 后文（仅供参考，不用翻译）\n```')
            prompt_parts.extend(next_original)
            prompt_parts.append('```')

        prompt_parts.append(
            '\n按以下格式输出（【新术语】如果没有可以留空）：\n'
            '```\n'
            '【译文】\n'
            'line1\n'
            'line2\n'
            '...\n'
            '【新术语】\n'
            '原文1 - 译文1\n'
            '原文2 - 译文2\n'
            '...\n'
            '```'
        )
        
        return '\n'.join(prompt_parts)
    
    def _find_terms_in_text(self, text_lines: List[str]) -> List[Term]:
        found = []
        text = ' '.join(text_lines)
        for term in self.terms.values():
            if term.source in text:
                found.append(term)
        return found

    def _get_text_chunk(self, 
                       lines: List[str], 
                       max_length: int, 
                       start_idx: int) -> Tuple[int, List[str]]:
        chunk = []
        current_length = 0
        i = start_idx
        
        while i < len(lines):
            line = lines[i].strip()
            line_length = len(line)

            if current_length + line_length > max_length and chunk:
                break
                
            chunk.append(line)
            current_length += line_length
            i += 1
            
        return i, chunk

    def _get_context(self, 
                    lines: List[str], 
                    translated: List[str],
                    current_idx: int,
                    window: List[str]) -> Tuple[List[str], List[str], List[str]]:
        prev_original = []
        prev_translated = []

        remaining_length = self.config.context_before
        i = len(translated) - 1

        while i >= 0 and remaining_length > 0:
            orig, trans = translated[i]
            line_length = len(orig)
            if remaining_length - line_length < 0 and prev_original:
                break
            prev_original.insert(0, orig)
            prev_translated.insert(0, trans)
            remaining_length -= line_length
            i -= 1

        next_start = current_idx + len(window)
        _, next_original = self._get_text_chunk(
            lines, self.config.context_after, next_start)

        return prev_original, prev_translated, next_original

    def _call_deepseek_api(self, prompt: str) -> str:
        return stream_generate(prompt)

    def _parse_response(self, response: str) -> Tuple[List[str], List[Term]]:
        translation_match = re.search(r'【译文】\s*(.*?)\s*(?:【新术语】|```)', response, re.DOTALL)
        translated_lines = [l.strip() for l in translation_match.group(1).split('\n') if l.strip()] if translation_match else []

        terms_match = re.search(r'【新术语】\s*(.*?)\s*```', response, re.DOTALL)
        new_terms = []
        if terms_match:
            for line in terms_match.group(1).split('\n'):
                if '-' in line:
                    parts = [p.strip() for p in line.split('-', 1)]
                    source = parts[0]
                    target_note = parts[1].split('（', 1)
                    target = target_note[0]
                    note = target_note[1][:-1] if len(target_note) > 1 else ''
                    new_terms.append(Term(source, target, note))
        
        return translated_lines, new_terms

    def _update_terms(self, new_terms: List[Term]):
        for term in new_terms:
            if term.source not in self.terms:
                self.terms[term.source] = term

    def translate(self, input_path: str, output_path: str, terms_path: str):
        with open(input_path, 'r', encoding='utf-8') as f:
            all_lines = [line.strip() for line in f.readlines()]

        total_lines = len(all_lines)
        current_idx = self.load_checkpoint(output_path, terms_path)

        while current_idx < total_lines:
            next_idx, window = self._get_text_chunk(
                all_lines, self.config.window_size, current_idx)

            prev_orig, prev_trans, next_orig = self._get_context(
                all_lines, self.translated_pairs, current_idx, window)

            prompt = self._build_prompt(window, prev_orig, prev_trans, next_orig)
            print(prompt)

            response = self._call_deepseek_api(prompt)

            translated, new_terms = self._parse_response(response)
            self._update_terms(new_terms)

            if len(translated) == len(window):
                for orig, trans in zip(window, translated):
                    self.translated_pairs.append((orig, trans))
            else:
                self.translated_pairs.append(('\n'.join(window), '\n'.join(translated)))

            self.save_checkpoint(output_path, terms_path)

            current_idx = next_idx

    def save_checkpoint(self, output_path: str, terms_path: str):
        output_data = [
            {self.config.source_label: orig, self.config.target_label: trans}
            for orig, trans in self.translated_pairs
        ]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=0)

        terms_json = [
            {'source': term.source, 'target': term.target, 'note': term.note}
            for term in self.terms.values()
        ]
        with open(terms_path, 'w', encoding='utf-8') as f:
            json.dump(terms_json, f, ensure_ascii=False, indent=0)

    def load_checkpoint(self, output_path: str, terms_path: str) -> int:
        current_idx = 0
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                output_data = json.load(f)
            self.translated_pairs = [
                (item[self.config.source_label], item[self.config.target_label])
                for item in output_data
            ]
            for source, _ in self.translated_pairs:
                current_idx += len(source.split('\n'))

        if os.path.exists(terms_path):
            with open(terms_path, 'r', encoding='utf-8') as f:
                terms_data = json.load(f)
            self.terms = {
                term['source']: Term(
                    source=term['source'],
                    target=term['target'],
                    note=term['note']
                )
                for term in terms_data
            }
        return current_idx


if __name__ == '__main__':
    config = TranslationConfig(
        window_size=2048,
        context_before=384,
        context_after=384,
        source_label='vi',
        target_label='zh',
        source_lang='越南语',
        target_lang='中文'
    )
    
    translator = NovelTranslator(config)

    translator.translate('vi.txt', 'zh.json', 'terms.json')
