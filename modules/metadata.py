# modules/metadata.py
import json
import logging # logging をインポート
import re # parse_parameters で使用
from typing import Any, Dict, Optional, Union # parse_parameters で使用
from PIL import Image, UnidentifiedImageError
from .constants import MetadataKeys # parse_parameters で使用 (キー名はここで定義されている想定)
# chardet はオプション
try:
    import chardet
except ImportError:
    chardet = None

logger = logging.getLogger(__name__) # logger を設定

# --- 元の decode_exif 関数 + logging ---
# (前々回の UTF-16 LE を先に ignore で試すバージョン)
def decode_exif(exif_data: bytes) -> str:
    """
    EXIFデータ（バイト列）をデコードして文字列に変換します。
    様々なエンコーディングを試行し、特にUTF-16の破損データにも対応を試みます。
    """
    if not isinstance(exif_data, bytes):
        logger.warning(f"decode_exif に bytes でないデータが渡されました: {type(exif_data)}")
        return str(exif_data)

    decoded_text = None
    tried_encodings = []

    try:
        unicode_prefix = b'UNICODE\x00\x00'
        prefix_pos = exif_data.find(unicode_prefix)

        if prefix_pos != -1:
            logger.debug("Found UNICODE prefix in EXIF data.")
            data_after_prefix = exif_data[prefix_pos + len(unicode_prefix):]
            tried_encodings.append('utf-16-be/le (UNICODE prefix, strict)')
            try:
                decoded_text = data_after_prefix.decode('utf-16-be', errors='strict')
                logger.debug("EXIF decoded as utf-16-be (after UNICODE prefix).")
            except UnicodeDecodeError:
                try:
                    decoded_text = data_after_prefix.decode('utf-16-le', errors='strict')
                    logger.debug("EXIF decoded as utf-16-le (after UNICODE prefix).")
                except UnicodeDecodeError as e_utf16_strict:
                    logger.debug(f"UNICODE prefix UTF-16 strict decoding failed: {e_utf16_strict}")
                    tried_encodings.append('utf-16-le/be (UNICODE prefix, ignore errors)') # 試行順変更
                    logger.debug(f"Attempting UTF-16 decoding with 'ignore' errors after strict failure.") # DEBUGレベルに変更

                    # ★★★ UTF-16 LE (ignore) を先に試す ★★★
                    try:
                         decoded_text = data_after_prefix.decode('utf-16-le', errors='ignore')
                         logger.debug("EXIF decoded as utf-16-le (after UNICODE prefix, ignore errors).")
                         if decoded_text:
                              return decoded_text # ★ 成功したらここで返す
                    except Exception as e_le_ignore:
                         logger.debug(f"UTF-16 LE (ignore) failed: {e_le_ignore}")

                    # ★★★ UTF-16 LE (ignore) がダメなら UTF-16 BE (ignore) を試す ★★★
                    if decoded_text is None or not decoded_text:
                         try:
                              decoded_text = data_after_prefix.decode('utf-16-be', errors='ignore')
                              logger.debug("EXIF decoded as utf-16-be (after UNICODE prefix, ignore errors).")
                              if decoded_text:
                                   return decoded_text # ★ 成功したらここで返す
                         except Exception as e_be_ignore:
                              logger.debug(f"UTF-16 BE (ignore) failed: {e_be_ignore}")

                    logger.warning(f"UNICODE prefix UTF-16 decoding (ignore errors) also failed. Raw data after prefix (first 50 bytes): {data_after_prefix[:50]}")
                    decoded_text = None # 他のエンコーディング試行へ


        else:
            logger.debug("UNICODE prefix not found in EXIF data.")

        # --- 他エンコーディングの試行 (プレフィックスがない、またはUTF-16デコード失敗時) ---

        # 2. UTF-8 (strict)
        if decoded_text is None:
             tried_encodings.append('utf-8')
             try:
                  if exif_data.startswith(b'\xef\xbb\xbf'):
                       decoded_text = exif_data[3:].decode('utf-8', errors='strict')
                       logger.debug("EXIF decoded as utf-8 (with BOM).")
                  else:
                       decoded_text = exif_data.decode('utf-8', errors='strict')
                       logger.debug("EXIF decoded as utf-8 (no BOM).")
             except UnicodeDecodeError:
                  logger.debug("EXIF decoding as utf-8 failed.")

        # 3. CP932 (strict)
        if decoded_text is None:
            tried_encodings.append('cp932')
            try:
                decoded_text = exif_data.decode('cp932', errors='strict')
                logger.debug("EXIF decoded as cp932 (Shift-JIS).")
            except (UnicodeDecodeError, LookupError):
                 logger.debug("EXIF decoding as cp932 failed.")

        # 4. chardet (オプション)
        if decoded_text is None and chardet:
             try:
                  detection = chardet.detect(exif_data)
                  encoding = detection['encoding']
                  confidence = detection['confidence']
                  if encoding and confidence > 0.7:
                      tried_encodings.append(f'chardet ({encoding}, conf={confidence:.2f})')
                      try:
                          decoded_text = exif_data.decode(encoding, errors='ignore')
                          logger.debug(f"EXIF decoded using chardet result '{encoding}' with 'ignore' errors.")
                          if decoded_text: return decoded_text
                      except (UnicodeDecodeError, LookupError):
                           logger.debug(f"Decoding bytes with chardet result {encoding} failed.")
                  else:
                       logger.debug(f"Chardet detection result ignored or low confidence: {detection}")
             except Exception as e_chardet:
                  logger.warning(f"Error during chardet detection: {e_chardet}")


        # 5. 最終フォールバック: 元のバイト列を UTF-8 (ignore errors) でデコード
        if decoded_text is None:
             tried_encodings.append('utf-8 (ignore errors)')
             logger.warning(f"All other decoding attempts failed for EXIF. Falling back to utf-8 with ignore errors. Tried: {', '.join(tried_encodings)}")
             logger.debug(f"Original EXIF bytes (first 100): {exif_data[:100]}")
             decoded_text = exif_data.decode('utf-8', errors='ignore')

        return decoded_text

    except Exception as e:
        logger.error(f"EXIFデータのデコード中に予期せぬエラーが発生しました: {e}", exc_info=True)
        try:
            return f"Decode error: {str(e)} | Raw bytes (approx): {exif_data.decode('utf-8', errors='ignore')}"
        except:
            return f"Decode error: {str(e)} | Cannot represent raw bytes."


# --- 元の parse_parameters 関数 + logging ---
# (前回のリファクタリング案 = 正規表現版を採用するのが推奨ですが、元のロジックに戻します)
def parse_parameters(text):
    params = {
        'positive_prompt': '',
        'negative_prompt': '',
        'generation_info': ''
    }
    if not isinstance(text, str): # 型チェック追加
         return params
    try:
        # Negative Prompt のマーカー
        neg_markers = ['Negative prompt:', 'negative_prompt:', 'neg_prompt:']
        neg_prompt_start = -1
        neg_marker_len = 0
        for marker in neg_markers:
            pos = text.find(marker) # 大文字小文字区別あり (元の挙動)
            if pos != -1:
                neg_prompt_start = pos
                neg_marker_len = len(marker)
                break

        # Generation Info のマーカー (Steps: が最も代表的か？)
        info_markers = ['Steps:', 'Model:', 'Size:', 'Seed:'] # 他のマーカーも考慮
        steps_start = -1
        for marker in info_markers:
            pos = text.find(marker)
            if pos != -1:
                 if steps_start == -1 or pos < steps_start:
                      steps_start = pos

        if neg_prompt_start != -1:
             params['positive_prompt'] = text[:neg_prompt_start].strip()
             if steps_start != -1 and steps_start > neg_prompt_start:
                  params['negative_prompt'] = text[neg_prompt_start + neg_marker_len:steps_start].strip()
                  params['generation_info'] = text[steps_start:].strip()
             else:
                  params['negative_prompt'] = text[neg_prompt_start + neg_marker_len:].strip()
        else:
             if steps_start != -1:
                  params['positive_prompt'] = text[:steps_start].strip()
                  params['generation_info'] = text[steps_start:].strip()
             else:
                  params['positive_prompt'] = text.strip()

    except Exception as e:
        logger.error(f"Error parsing parameters: {e}", exc_info=True)
        params['positive_prompt'] = text.strip()
        params['negative_prompt'] = ''
        params['generation_info'] = ''

    return params


# --- 元の extract_metadata 関数 + logging ---
def extract_metadata(image_path):
    try:
        logger.debug(f"Extracting metadata (original logic) from: {image_path}")
        with Image.open(image_path) as img:
            metadata = {}
            if img.info: # img.info が存在するかチェック
                 logger.debug(f"Found {len(img.info)} items in img.info")
                 for key, value in img.info.items():
                     parsed_value = value
                     original_type = type(value).__name__
                     logger.debug(f"Processing key: '{key}', type: {original_type}")
                     try:
                         if key == 'exif' and isinstance(value, bytes):
                             parsed_value = decode_exif(value) # exif のみ decode_exif を使用
                             logger.debug(f"Decoded EXIF. Result type: {type(parsed_value).__name__}")
                         elif key == 'parameters' and isinstance(value, bytes):
                             logger.debug(f"Decoding 'parameters' bytes using utf-8 (ignore).")
                             parsed_value = value.decode('utf-8', errors='ignore')
                         elif isinstance(value, str):
                              parsed_value = value
                              try:
                                   cleaned_value = value.strip().strip('\x00')
                                   if (cleaned_value.startswith('{') and cleaned_value.endswith('}')) or \
                                      (cleaned_value.startswith('[') and cleaned_value.endswith(']')):
                                        parsed_value = json.loads(cleaned_value)
                                        logger.debug(f"Successfully parsed string value of key '{key}' as JSON.")
                              except json.JSONDecodeError:
                                   logger.debug(f"String value of key '{key}' is not valid JSON.")
                              except Exception as json_err:
                                   logger.warning(f"キー '{key}' のJSONパース中にエラー: {json_err}", exc_info=False)
                         # else: 他の型はそのまま

                         metadata[key] = parsed_value
                         log_value = str(parsed_value)
                         if len(log_value) > 100: log_value = log_value[:100] + "..."
                         logger.debug(f"Stored metadata for key '{key}'. Type: {type(parsed_value).__name__}, Value (preview): {log_value}")

                     except Exception as e_inner:
                          logger.error(f"メタデータ項目 '{key}' (type: {original_type}) の処理中にエラー: {e_inner}", exc_info=True)
                          metadata[key] = f"Error processing {key}: {str(e_inner)}"

            else:
                 logger.info(f"No metadata found in img.info for {image_path}")

            # プロンプト情報の解析 (元のロジック)
            params = {'positive_prompt': '', 'negative_prompt': '', 'generation_info': ''}
            param_text = None
            if 'parameters' in metadata and isinstance(metadata['parameters'], str):
                param_text = metadata['parameters']
                logger.info("Using 'parameters' key (str) for prompt parsing.")
            elif 'exif' in metadata and isinstance(metadata['exif'], str):
                param_text = metadata['exif']
                logger.info("Using 'exif' key (str) for prompt parsing.")

            if param_text:
                params = parse_parameters(param_text) # ここは元の parse_parameters
                log_positive = params['positive_prompt'][:50] + ('...' if len(params['positive_prompt']) > 50 else '')
                log_negative = params['negative_prompt'][:50] + ('...' if len(params['negative_prompt']) > 50 else '')
                log_info = params['generation_info'][:50] + ('...' if len(params['generation_info']) > 50 else '')
                logger.debug(f"Parsed parameters: Positive='{log_positive}', Negative='{log_negative}', Info='{log_info}'")

            metadata.update(params)
            return json.dumps(metadata, indent=4, ensure_ascii=False, default=str)

    except FileNotFoundError:
        logger.error(f"画像ファイルが見つかりません: {image_path}")
        return json.dumps({"error": f"File not found: {image_path}"}, indent=4)
    except UnidentifiedImageError:
        logger.error(f"画像ファイルとして認識できません: {image_path}")
        return json.dumps({"error": f"Cannot identify image file: {image_path}"}, indent=4)
    except IOError as e_io:
        logger.error(f"画像ファイルの読み込み中にI/Oエラーが発生しました: {image_path}, Error: {e_io}", exc_info=True)
        return json.dumps({"error": f"IO Error reading file: {str(e_io)}"}, indent=4)
    except Exception as e:
        logger.critical(f"メタデータ抽出中に予期せぬエラーが発生しました: {image_path}, Error: {e}", exc_info=True)
        return json.dumps({"error": f"Unexpected error during metadata extraction: {str(e)}"}, indent=4)