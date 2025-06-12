from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import urljoin, urlparse
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SentenceScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def add_random_delay(self):
        """Add random delay to avoid being detected as bot"""
        delay = random.uniform(1, 3)
        time.sleep(delay)
    
    def scrape_sentencedict(self, word):
        """Scrape sentences from sentencedict.com"""
        try:
            url = f"https://sentencedict.com/{word}.html"
            self.add_random_delay()
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract sentences from both #all and #student divs
            sentences = []
            selectors = ['#all > div', '#student > div']
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    if text and not text.startswith('Sentencedict.com'):
                        sentences.append(text)
            
            # Extract word image if available
            image_url = None
            img_element = soup.select_one('#imageId img, #imageId2 img')
            if img_element and img_element.get('src'):
                image_url = urljoin(url, img_element['src'])
            
            # Process sentences (remove numbers, parentheses, etc.)
            processed_sentences = self.process_sentences(sentences)
            
            return {
                'sentences': processed_sentences,
                'image_url': image_url,
                'source': 'sentencedict.com'
            }
            
        except Exception as e:
            logger.error(f"Error scraping sentencedict for '{word}': {str(e)}")
            return None
    
    def scrape_cambridge(self, word):
        """Scrape sentences from Cambridge Dictionary"""
        try:
            url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
            self.add_random_delay()
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            sentences = []
            # Cambridge uses .eg class for example sentences
            examples = soup.select('.eg')
            
            for example in examples:
                text = example.get_text(strip=True)
                if text:
                    sentences.append(text)
            
            return {
                'sentences': sentences[:20],  # Limit to 20 sentences
                'image_url': None,
                'source': 'cambridge.org'
            }
            
        except Exception as e:
            logger.error(f"Error scraping Cambridge for '{word}': {str(e)}")
            return None
    
    def scrape_yourdictionary(self, word):
        """Scrape sentences from YourDictionary"""
        try:
            url = f"https://sentence.yourdictionary.com/{word}"
            self.add_random_delay()
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            sentences = []
            # YourDictionary uses specific classes for sentences
            sentence_elements = soup.select('.sentence-item .sentence, .example-sentence')
            
            for element in sentence_elements:
                text = element.get_text(strip=True)
                if text:
                    sentences.append(text)
            
            return {
                'sentences': sentences[:20],
                'image_url': None,
                'source': 'yourdictionary.com'
            }
            
        except Exception as e:
            logger.error(f"Error scraping YourDictionary for '{word}': {str(e)}")
            return None
    
        def process_sentences(self, sentences):
        """Clean and process sentences"""
        regex = re.compile(r'(\(\d+\)|\(.*?\)|\d+\.)|^\d+[\.,]|^\d+')
        processed = []
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence.strip():
                continue
                
            cleaned = regex.sub(' ', sentence).strip()
            
            # Clean up multiple spaces
            cleaned = re.sub(r'\s+', ' ', cleaned)
            
            # Skip very short sentences or obvious non-sentences
            if len(cleaned) < 10 or cleaned.lower().startswith(('show all', 'random good')):
                continue
                
            # Add numbering
            processed.append(f"{i}. {cleaned}")
            
            # Limit to 30 sentences
            if len(processed) >= 30:
                break
                
        return processed

# Initialize scraper
scraper = SentenceScraper()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'sentence-scraper'})

@app.route('/sentences/<word>', methods=['GET'])
def get_sentences(word):
    """Get sentences for a specific word"""
    if not word or len(word.strip()) == 0:
        return jsonify({'error': 'Word parameter is required'}), 400
    
    # Sanitize word input
    word = re.sub(r'[^a-zA-Z\-]', '', word.lower().strip())
    
    if not word:
        return jsonify({'error': 'Invalid word format'}), 400
    
    logger.info(f"Fetching sentences for word: {word}")
    
    # Try multiple sources
    sources = [
        scraper.scrape_sentencedict,
        scraper.scrape_cambridge,
        scraper.scrape_yourdictionary
    ]
    
    all_results = []
    
    for source_func in sources:
        try:
            result = source_func(word)
            if result and result['sentences']:
                all_results.append(result)
        except Exception as e:
            logger.error(f"Error with source {source_func.__name__}: {str(e)}")
            continue
    
    if not all_results:
        return jsonify({
            'word': word,
            'sentences': ['No sentences found for this word.'],
            'image_url': None,
            'sources': [],
            'total_sentences': 0
        })
    
    # Combine results
    combined_sentences = []
    image_url = None
    sources_used = []
    
    for result in all_results:
        combined_sentences.extend(result['sentences'])
        sources_used.append(result['source'])
        if result['image_url'] and not image_url:
            image_url = result['image_url']
    
    # Remove duplicates while preserving order
    seen = set()
    unique_sentences = []
    for sentence in combined_sentences:
        # Create a simplified version for comparison
        simple = re.sub(r'^\d+\.\s*', '', sentence.lower())
        if simple not in seen:
            seen.add(simple)
            unique_sentences.append(sentence)
    
    return jsonify({
        'word': word,
        'sentences': unique_sentences[:30],  # Limit to 30 sentences
        'image_url': image_url,
        'sources': list(set(sources_used)),
        'total_sentences': len(unique_sentences)
    })

@app.route('/batch-sentences', methods=['POST'])
def get_batch_sentences():
    """Get sentences for multiple words"""
    data = request.get_json()
    
    if not data or 'words' not in data:
        return jsonify({'error': 'Words array is required'}), 400
    
    words = data['words']
    if not isinstance(words, list) or len(words) == 0:
        return jsonify({'error': 'Words must be a non-empty array'}), 400
    
    if len(words) > 10:  # Limit batch size
        return jsonify({'error': 'Maximum 10 words per batch'}), 400
    
    results = {}
    
    for word in words:
        word = re.sub(r'[^a-zA-Z\-]', '', str(word).lower().strip())
        if word:
            try:
                # Use only primary source for batch to reduce load
                result = scraper.scrape_sentencedict(word)
                if result:
                    results[word] = result
                else:
                    results[word] = {
                        'sentences': ['No sentences found.'],
                        'image_url': None,
                        'source': 'none'
                    }
            except Exception as e:
                logger.error(f"Error processing word '{word}': {str(e)}")
                results[word] = {
                    'sentences': ['Error fetching sentences.'],
                    'image_url': None,
                    'source': 'error'
                }
    
    return jsonify({'results': results})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)