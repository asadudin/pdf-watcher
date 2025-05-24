import os
import time
import base64
import subprocess
import json
import datetime
import sys
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import io
from google.cloud import vision

# Configure logging with timestamps
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)03d %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger('pdf_watcher')

# Create logger instance
logger = setup_logging()

# Override print to use our logger
def print(*args, **kwargs):
    logger.info(' '.join(map(str, args)), **kwargs)

class PDFHandler(FileSystemEventHandler):
    def __init__(self):
        self.watch_dir = "/images"
        self.input_file = os.path.join(self.watch_dir, "input.pdf")
        
    def on_created(self, event):
        if not event.is_directory and event.src_path == self.input_file:
            # Small delay to ensure the file is ready for processing
            time.sleep(1)
            self.process_pdf()
    
    def is_file_stable(self, file_path, check_interval=1.0, stable_period=2.0):
        """Check if file size remains constant for the specified period."""
        print(f"🔍 Monitoring file size stability for {stable_period} seconds...")
        last_size = -1
        stable_start = None
        
        while True:
            try:
                current_size = os.path.getsize(file_path)
                current_time = time.time()
                
                if current_size == 0:
                    print("⚠️ File size is 0, waiting for content...")
                    time.sleep(check_interval)
                    continue
                    
                if current_size != last_size:
                    print(f"📊 File size changed: {last_size} → {current_size} bytes")
                    last_size = current_size
                    stable_start = current_time
                elif stable_start and (current_time - stable_start) >= stable_period:
                    print(f"✅ File size stable at {current_size} bytes for {stable_period} seconds")
                    return True
                    
            except FileNotFoundError:
                print(f"❌ File disappeared: {file_path}")
                return False
                
            time.sleep(check_interval)
    
    def process_pdf(self):
        start_time = datetime.datetime.now()
        print(f"🖨️ Found input.pdf. Processing... [Started at: {start_time.strftime('%H:%M:%S')}]")
        try:
            # Wait for the file to be completely written
            stability_start = datetime.datetime.now()
            if not self.is_file_stable(self.input_file):
                print("❌ File is not stable or was removed during check")
                return
            stability_end = datetime.datetime.now()
            stability_duration = (stability_end - stability_start).total_seconds()
            print(f"⏱️ File stability check took {stability_duration:.2f} seconds")
                
            file_size = os.path.getsize(self.input_file)
            print(f"📄 Final file size: {file_size} bytes")
            
            # First, try a simple PDF info command to check if the file is valid
            print("🔍 Checking PDF file...")
            pdf_info_start = datetime.datetime.now()
            try:
                check_cmd = ["pdfinfo", self.input_file]
                check_result = subprocess.run(
                    check_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                print(f"📄 PDF Info:\n{check_result.stdout}")
            except Exception as e:
                print(f"⚠️ PDF info check failed: {e}")
            pdf_info_end = datetime.datetime.now()
            pdf_info_duration = (pdf_info_end - pdf_info_start).total_seconds()
            print(f"⏱️ PDF info check took {pdf_info_duration:.2f} seconds")

            # Convert PDF to JPG using ImageMagick
            conversion_start = datetime.datetime.now()
            print(f"🚀 Starting PDF to JPG conversion at: {conversion_start.strftime('%H:%M:%S')}")
            cmd = [
                "timeout", "600",  # 10 minute timeout for full document
                "convert",
                "-density", "200",  # Good balance of quality and speed
                "-quality", "90",
                self.input_file,
                os.path.join(self.watch_dir, "output-%d.jpg")
            ]
            print(f"🚀 Running command: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(
                    cmd, 
                    check=False, 
                    capture_output=True, 
                    text=True,
                    timeout=610  # Slightly more than the command timeout
                )
                
                conversion_end = datetime.datetime.now()
                conversion_duration = (conversion_end - conversion_start).total_seconds()
                print(f"⏱️ PDF to JPG conversion took {conversion_duration:.2f} seconds")
                
                if result.returncode == 124:  # 124 is the exit code for timeout
                    print("❌ PDF conversion timed out")
                    return
                elif result.returncode != 0:
                    print(f"❌ Command failed with code {result.returncode}")
                    if result.stderr:
                        print(f"STDERR: {result.stderr.strip()}")
                    return
                
                print("✅ PDF to JPG conversion completed")
                
                # Find all output-*.jpg files
                jpg_files = sorted([
                    f for f in os.listdir(self.watch_dir)
                    if f.startswith('output-') and f.endswith('.jpg')
                ])
                
                if not jpg_files:
                    print("❌ No output JPG files found")
                    return
                    
                print(f"✅ Converted to {len(jpg_files)} image files")
                
                # Convert JPG to base64 and save to files
                base64_start = datetime.datetime.now()
                print(f"🔄 Starting JPG to base64 conversion at: {base64_start.strftime('%H:%M:%S')}")
                
                for jpg_file in jpg_files:
                    jpg_path = os.path.join(self.watch_dir, jpg_file)
                    file_stat = os.stat(jpg_path)
                    file_size = file_stat.st_size
                    file_mtime = time.ctime(file_stat.st_mtime)
                    
                    # Convert to base64
                    b64_content = self.jpg_to_base64(jpg_path)
                    b64_file = jpg_file.replace('.jpg', '.b64')
                    b64_path = os.path.join(self.watch_dir, b64_file)
                    
                    with open(b64_path, 'w') as f:
                        f.write(b64_content)
                        
                    print(f"  - {jpg_file} (Size: {file_size} bytes, Modified: {file_mtime})")
                    print(f"  Base64 saved to: {b64_file} (Length: {len(b64_content)} characters)")
                
                base64_end = datetime.datetime.now()
                base64_duration = (base64_end - base64_start).total_seconds()
                print(f"⏱️ JPG to base64 conversion took {base64_duration:.2f} seconds for {len(jpg_files)} files")
                print(f"✅ Created {len(jpg_files)} individual base64 files")
                
                # Extract text from all base64 files

                # Extract text from all output-*.b64 files and save to extracted_text.txt
                self.extract_text_from_b64_images()

            except subprocess.TimeoutExpired:
                print("❌ PDF conversion timed out (subprocess timeout)")
                return
            except Exception as e:
                print(f"❌ Error during PDF conversion: {str(e)}")
                return
                
        except Exception as e:
            print(f"❌ An error occurred: {e}")
        finally:
            end_time = datetime.datetime.now()
            total_duration = (end_time - start_time).total_seconds()
            print(f"⏱️ Total processing time: {total_duration:.2f} seconds [Completed at: {end_time.strftime('%H:%M:%S')}]")
            
            # Save overall timing to a file
            try:
                timing_summary_path = os.path.join(self.watch_dir, 'processing_timing.json')
                with open(timing_summary_path, 'w') as timing_file:
                    json.dump({
                        'start_time': start_time.isoformat(),
                        'end_time': end_time.isoformat(),
                        'total_duration_seconds': total_duration,
                        'pdf_path': self.input_file,
                        'pdf_size_bytes': os.path.getsize(self.input_file) if os.path.exists(self.input_file) else None
                    }, timing_file, indent=2)
                print(f"✅ Overall timing information saved to {timing_summary_path}")
            except Exception as e:
                print(f"⚠️ Failed to save timing information: {e}")
    
    @staticmethod
    def jpg_to_base64(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")

    def extract_text_from_b64_images(self):
        """
        Extract text from all output-*.b64 files in the watch directory using Google Cloud Vision API
        and save the combined text to extracted_text.txt.
        
        Also extracts detailed information including text blocks, paragraphs, words,
        and their bounding boxes, saving this structured data to a JSON file.
        """
        extraction_start = datetime.datetime.now()
        print(f"🔍 Starting text extraction at: {extraction_start.strftime('%H:%M:%S')}")
        
        b64_files = sorted([
            f for f in os.listdir(self.watch_dir)
            if f.startswith('output-') and f.endswith('.b64')
        ])
        if not b64_files:
            print("❌ No .b64 files found for OCR.")
            return
            
        client = vision.ImageAnnotatorClient()
        all_text = []
        all_structured_data = []
        page_timings = []
        
        for b64_file in b64_files:
            page_start = datetime.datetime.now()
            b64_path = os.path.join(self.watch_dir, b64_file)
            page_num = int(b64_file.split('-')[1].split('.')[0])  # Extract page number from filename
            
            with open(b64_path, 'r') as f:
                b64_content = f.read()
            
            # Track API call time specifically
            api_call_start = datetime.datetime.now()
            image = vision.Image(content=base64.b64decode(b64_content))
            
            # Use document_text_detection for more structured results
            # This is better for multi-column text and documents
            response = client.document_text_detection(image=image)
            api_call_end = datetime.datetime.now()
            api_call_duration = (api_call_end - api_call_start).total_seconds()
            
            if response.error.message:
                print(f"❌ Vision API error for {b64_file}: {response.error.message}")
                continue
                
            # Get the full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ''
            
            # Extract structured data
            page_data = {
                'page_number': page_num,
                'full_text': full_text,
                'blocks': []
            }
            
            # Process each page
            for page in response.full_text_annotation.pages:
                # Process each block (typically paragraphs or sections)
                for block_idx, block in enumerate(page.blocks):
                    block_data = {
                        'block_id': block_idx,
                        'confidence': block.confidence,
                        'bounding_box': self._get_bounding_box(block.bounding_box),
                        'paragraphs': []
                    }
                    
                    # Process each paragraph within the block
                    for para_idx, paragraph in enumerate(block.paragraphs):
                        para_text = ''
                        para_data = {
                            'paragraph_id': para_idx,
                            'confidence': paragraph.confidence,
                            'bounding_box': self._get_bounding_box(paragraph.bounding_box),
                            'words': []
                        }
                        
                        # Process each word within the paragraph
                        for word_idx, word in enumerate(paragraph.words):
                            word_text = ''.join([symbol.text for symbol in word.symbols])
                            para_text += word_text + ' '
                            
                            # Get word details
                            word_data = {
                                'word_id': word_idx,
                                'text': word_text,
                                'confidence': word.confidence,
                                'bounding_box': self._get_bounding_box(word.bounding_box),
                                'symbols': []
                            }
                            
                            # Get symbol details (characters)
                            for symbol in word.symbols:
                                symbol_data = {
                                    'text': symbol.text,
                                    'confidence': symbol.confidence
                                }
                                
                                # Check for special properties
                                if symbol.property.detected_break.type != 0:  # If there's a break
                                    break_type = vision.TextAnnotation.DetectedBreak.BreakType(symbol.property.detected_break.type).name
                                    symbol_data['break_type'] = break_type
                                    
                                word_data['symbols'].append(symbol_data)
                                
                            para_data['words'].append(word_data)
                            
                        para_data['text'] = para_text.strip()
                        block_data['paragraphs'].append(para_data)
                        
                    page_data['blocks'].append(block_data)
            
            page_end = datetime.datetime.now()
            page_duration = (page_end - page_start).total_seconds()
            
            # Record timing information
            page_timing = {
                'page': page_num,
                'file': b64_file,
                'total_time': page_duration,
                'api_call_time': api_call_duration,
                'text_length': len(full_text)
            }
            page_timings.append(page_timing)
            
            print(f"✅ Extracted text from {b64_file}: {len(full_text)} characters (API: {api_call_duration:.2f}s, Total: {page_duration:.2f}s)")
            
            all_text.append(full_text)
            all_structured_data.append(page_data)
        
        # Calculate average times
        if page_timings:
            avg_total_time = sum(timing['total_time'] for timing in page_timings) / len(page_timings)
            avg_api_time = sum(timing['api_call_time'] for timing in page_timings) / len(page_timings)
            print(f"📊 Average processing time per page: {avg_total_time:.2f}s (API calls: {avg_api_time:.2f}s)")
        
        # Save timing information
        timing_path = os.path.join(self.watch_dir, 'extraction_timing.json')
        with open(timing_path, 'w') as timing_file:
            json.dump({
                'pages': page_timings,
                'total_pages': len(page_timings),
                'start_time': extraction_start.isoformat(),
                'end_time': datetime.datetime.now().isoformat(),
                'total_duration': (datetime.datetime.now() - extraction_start).total_seconds()
            }, timing_file, indent=2)
            
        # Save the plain text
        text_save_start = datetime.datetime.now()
        output_path = os.path.join(self.watch_dir, 'extracted_text.txt')
        with open(output_path, 'w') as out_file:
            out_file.write('\n\n'.join(all_text))
        
        # Save the structured data as JSON
        structured_output_path = os.path.join(self.watch_dir, 'extracted_structured_text.json')
        with open(structured_output_path, 'w') as json_file:
            json.dump(all_structured_data, json_file, indent=2)
        
        extraction_end = datetime.datetime.now()
        extraction_duration = (extraction_end - extraction_start).total_seconds()
        file_save_duration = (extraction_end - text_save_start).total_seconds()
        
        print(f"⏱️ Total text extraction took {extraction_duration:.2f} seconds for {len(b64_files)} pages")
        print(f"⏱️ File saving took {file_save_duration:.2f} seconds")
        print(f"✅ All extracted text saved to {output_path}")
        print(f"✅ Structured text data saved to {structured_output_path}")
        print(f"✅ Timing information saved to {timing_path}")
        
    def _get_bounding_box(self, bounding_box):
        """
        Helper method to convert Vision API bounding box to a dictionary.
        """
        return {
            'vertices': [
                {'x': vertex.x, 'y': vertex.y}
                for vertex in bounding_box.vertices
            ]
        }
from dotenv import load_dotenv
load_dotenv()
def main():
    # Print startup banner with timestamp
    print("📝 PDF Watcher starting up")
    print(f"🔧 Python version: {sys.version}")
    print(f"🔧 Watch directory: {os.getcwd()}")
    
    event_handler = PDFHandler()
    observer = Observer()
    
    try:
        print(f"👀 Setting up observer for directory: {event_handler.watch_dir}")
        observer.schedule(event_handler, event_handler.watch_dir, recursive=False)
        observer.start()
        print("✅ Observer started successfully")
        print("🔄 Ready to process PDF files")
        print("ℹ️  Press Ctrl+C to stop")
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Received keyboard interrupt, shutting down...")
        observer.stop()
    except Exception as e:
        print(f"❌ Error in observer: {str(e)}")
    
    print("🔄 Stopping observer...")
    observer.join()
    print("✅ Observer stopped, exiting program")

if __name__ == "__main__":
    main()
