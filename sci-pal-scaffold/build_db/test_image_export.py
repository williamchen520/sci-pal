"""
Simple test: can Docling actually export images?
"""
import os
from pathlib import Path
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import ImageRefMode

# Configure
pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = False
pipeline_options.do_table_structure = True
pipeline_options.generate_parsed_pages = True

# Try multiple possible setting names
print("Testing image generation settings...")
print(f"  generate_picture_images = {getattr(pipeline_options, 'generate_picture_images', 'NOT FOUND')}")
print(f"  images_scale = {getattr(pipeline_options, 'images_scale', 'NOT FOUND')}")

# Try to set it
try:
    pipeline_options.generate_picture_images = True
    print(f"  ✅ Set generate_picture_images = {pipeline_options.generate_picture_images}")
except Exception as e:
    print(f"  ❌ Failed: {e}")

# List all attributes with 'image' or 'picture'
print("\nAll image/picture related options:")
for attr in dir(pipeline_options):
    if 'image' in attr.lower() or 'picture' in attr.lower():
        if not attr.startswith('_'):
            try:
                val = getattr(pipeline_options, attr)
                print(f"  {attr} = {val}")
            except:
                pass

converter = DocumentConverter(
    format_options={
        "pdf": PdfFormatOption(pipeline_options=pipeline_options)
    }
)

# Test with one PDF
pdf_path = "documents/1-s2.0-S0022175914002968-main.pdf"
if not os.path.exists(pdf_path):
    print(f"\n❌ PDF not found: {pdf_path}")
    print("Please run this from the sciPal root directory")
    exit(1)

print(f"\nParsing {pdf_path}...")
result = converter.convert(pdf_path)
doc = result.document

# Check if we can get images
print("\nChecking picture items...")
from docling_core.types.doc import PictureItem
from docling_core.types.doc.document import DoclingDocument

pic_count = 0
for item, level in doc.iterate_items():
    if isinstance(item, PictureItem):
        pic_count += 1
        print(f"\n  Picture {pic_count}:")
        print(f"    item.image = {type(item.image)}")
        try:
            img = item.get_image(doc)
            print(f"    get_image(doc) = {type(img)}")
            if img is not None:
                print(f"    Image size: {img.size}")
        except Exception as e:
            print(f"    get_image error: {e}")

print(f"\nTotal pictures found: {pic_count}")

# Also try save_as_markdown with referenced images
print("\nTrying save_as_markdown with REFERENCED mode...")
output_dir = Path("test_output")
output_dir.mkdir(exist_ok=True)

try:
    doc.save_as_markdown(
        output_dir / "test.md",
        image_mode=ImageRefMode.REFERENCED,
        artifacts_dir=output_dir / "images"
    )
    print(f"  ✅ Saved markdown to {output_dir / 'test.md'}")

    # Check if images were created
    images_dir = output_dir / "images"
    if images_dir.exists():
        images = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
        print(f"  ✅ Found {len(images)} image files in {images_dir}")
        for img in images[:5]:
            print(f"    - {img.name} ({img.stat().st_size / 1024:.1f} KB)")
    else:
        print(f"  ❌ No images directory found at {images_dir}")
except Exception as e:
    print(f"  ❌ save_as_markdown failed: {type(e).__name__}: {e}")
