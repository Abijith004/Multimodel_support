from PIL import Image
import pytesseract  # For OCR
from transformers import pipeline

# Initialize OCR and image captioning
image_captioner = pipeline("image-to-text", model="nlpconnect/vit-gpt2-image-captioning")

def image_to_text(image_path):
    """Process images to extract both text and contextual description"""
    try:
        # 1. Extract text via OCR
        img = Image.open(image_path)
        ocr_text = pytesseract.image_to_string(img)
        
        # 2. Generate contextual description
        caption = image_captioner(image_path)[0]['generated_text']
        
        return f"Extracted text: {ocr_text}\nImage context: {caption}"
    
    except Exception as e:
        return f"Error processing image: {str(e)}"