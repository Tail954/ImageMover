# modules/metadata.py
import json
from PIL import Image

def decode_exif(exif_data):
    if isinstance(exif_data, bytes):
        try:
            unicode_start = exif_data.find(b'UNICODE\x00\x00')
            if unicode_start != -1:
                data = exif_data[unicode_start + 8:]
                try:
                    return data.decode('utf-16-be')
                except UnicodeDecodeError:
                    return data.decode('utf-16-le')
            else:
                return exif_data.decode('utf-8', errors='ignore')
        except Exception as e:
            return f"Decode error: {str(e)}"
    return str(exif_data)

def parse_parameters(text):
    params = {
        'positive_prompt': '',
        'negative_prompt': '',
        'generation_info': ''
    }
    try:
        neg_markers = ['Negative prompt:', 'negative_prompt:', 'neg_prompt:']
        neg_prompt_start = -1
        for marker in neg_markers:
            pos = text.find(marker)
            if pos != -1:
                neg_prompt_start = pos
                break
        info_markers = ['Steps:', 'Model:', 'Size:', 'Seed:']
        steps_start = -1
        for marker in info_markers:
            pos = text.find(marker)
            if pos != -1 and (steps_start == -1 or pos < steps_start):
                steps_start = pos
        if neg_prompt_start != -1:
            params['positive_prompt'] = text[:neg_prompt_start].strip()
            if steps_start != -1:
                marker_found = [m for m in neg_markers if text[neg_prompt_start:].startswith(m)]
                if marker_found:
                    neg_length = len(marker_found[0])
                    params['negative_prompt'] = text[neg_prompt_start + neg_length:steps_start].strip()
                    params['generation_info'] = text[steps_start:].strip()
                else:
                    params['negative_prompt'] = text[neg_prompt_start:].strip()
            else:
                params['negative_prompt'] = text[neg_prompt_start:].strip()
        else:
            if steps_start != -1:
                params['positive_prompt'] = text[:steps_start].strip()
                params['generation_info'] = text[steps_start:].strip()
            else:
                params['positive_prompt'] = text.strip()
    except Exception as e:
        print(f"Error parsing parameters: {e}")
    return params

def extract_metadata(image_path):
    try:
        with Image.open(image_path) as img:
            metadata = {}
            for key, value in img.info.items():
                try:
                    if key == 'exif':
                        metadata[key] = decode_exif(value)
                    elif key == 'parameters':
                        metadata[key] = value
                    elif isinstance(value, str):
                        try:
                            json_value = json.loads(value)
                            metadata[key] = json_value
                        except Exception:
                            metadata[key] = value
                    else:
                        metadata[key] = value
                except Exception as e:
                    metadata[key] = f"Error parsing {key}: {str(e)}"
            params = {'positive_prompt': '', 'negative_prompt': '', 'generation_info': ''}
            if 'parameters' in metadata:
                params = parse_parameters(metadata['parameters'])
            elif 'exif' in metadata:
                params = parse_parameters(metadata['exif'])
            metadata.update(params)
            return json.dumps(metadata, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)
