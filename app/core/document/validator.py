import base64
import os
import json
from typing import List, Any, Dict
from openai import OpenAI
from io import BytesIO
from PIL import Image

def image_to_base64(image_path: str) -> str:
    """Read image from path and convert to base64 string."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB to ensure compatibility (e.g. if RGBA)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return ""

def validate_json_with_images(image_paths: List[str], json_content: Any) -> Dict:
    """
    Validate the extracted JSON against the provided images using GPT-4o.
    
    Args:
        image_paths: List of absolute paths to the page images.
        json_content: The extracted JSON object or string to validate.
        
    Returns:
        Dict containing the validation review.
    """
    
    # Ensure json_content is a string for the prompt
    if not isinstance(json_content, str):
        json_string = json.dumps(json_content, indent=2, ensure_ascii=False)
    else:
        json_string = json_content

    # Prepare image messages
    image_contents = []
    for img_path in image_paths:
        if os.path.exists(img_path):
            b64_img = image_to_base64(img_path)
            if b64_img:
                image_contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}"
                    }
                })
        else:
            print(f"Warning: Validation image not found at {img_path}")

    if not image_contents:
        return {"error": "No valid images found for validation"}

    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a STRICT OCR validation engine.\n"
                        "You receive a RAW JSON STRING.\n"
                        "Validate it against the PDF images.\n\n"
                        "RULES:\n"
                        "- Do NOT fix values\n"
                        "- Do NOT infer missing data\n"
                        "- Only report mistakes\n"
                        "- Also report structural mistakes\n",
                        "- Check the if it is writing multiple invoices under JSON Correctly."
                        "- Output MUST be valid JSON with a 'mistakes' list and a 'score' (0-100)\n"
                        "- If perfect, 'mistakes' should be empty and 'score' 100.\n"
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Below is the extracted JSON as RAW STRING.\n"
                                "Compare it STRICTLY against the provided document pages.\n\n"
                                f"Extracted JSON:\n{json_string}"
                            )
                        },
                        *image_contents
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        if content:
            return json.loads(content)
        return {"error": "Empty response from GPT-4o"}

    except Exception as e:
        print(f"Validation error: {e}")
        return {"error": str(e)}
