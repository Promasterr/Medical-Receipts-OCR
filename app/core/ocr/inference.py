"""
OCR inference using vLLM API with async batch processing.
"""
import asyncio
import time
from typing import List, Dict, Any
from PIL import Image
import base64
from io import BytesIO
from app.models.ml_models import model_manager
from app.config import settings


def image_to_base64(image: Image.Image) -> str:
    """
    Converts a PIL Image object to a base64 encoded string.
    
    Args:
        image: PIL Image object
        
    Returns:
        Base64 encoded string of the image
    """
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    return img_base64


async def _run_single_inference_task(item: Dict, max_new_tokens: int):
    """
    Performs a single, non-blocking API call.
    Returns the generated content or the Exception object if an error occurs.
    
    Args:
        item: Dictionary containing 'image' and 'prompt'
        max_new_tokens: Maximum tokens to generate
        
    Returns:
        Generated text content or Exception object
    """
    try:
        client = model_manager.vllm_client
        
        # Convert PIL Image to base64
        img_b64 = image_to_base64(item["image"])
        
        # Build messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                    },
                    {"type": "text", "text": item["prompt"]}
                ]
            }
        ]
        
        # API call
        response = await client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=messages,
            max_tokens=max_new_tokens,
            temperature=0.0
        )
        
        content = response.choices[0].message.content
        return content
    
    except Exception as e:
        return e


async def run_batch_inference(batch_data: List[Dict], max_new_tokens: int = 8192) -> List[Any]:
    """
    Runs inference on a list of images and prompts CONCURRENTLY.
    
    Args:
        batch_data: List of dictionaries, each containing:
            - 'image': PIL Image object
            - 'prompt': str
            - 'mode': str (optional)
            - 'original_path': str (optional)
        max_new_tokens: Maximum tokens to generate per request
        
    Returns:
        List of strings (generated text) or Exception objects
    """
    start_time = time.time()
    
    # Create tasks
    tasks = [
        _run_single_inference_task(item, max_new_tokens)
        for item in batch_data
    ]
    
    # Run all concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    
    # Count errors
    errors = [r for r in results if isinstance(r, Exception)]
    success = len(results) - len(errors)
    
    print(f"Batch inference completed: {success}/{len(results)} succeeded in {elapsed:.2f}s")
    
    if errors:
        print(f"Errors encountered: {len(errors)}")
        for i, err in enumerate(errors, 1):
            print(f"  Error {i}: {err}")
    
    return results
