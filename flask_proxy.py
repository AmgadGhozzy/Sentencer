from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
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
    
    def scrape_sentencedict(self, word):
        """Scrape sentences from sentencedict.com"""
        try:
            url = f"https://sentencedict.com/{word}.html"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract sentences from both #all and #student divs
            sentences = []
            selectors = ['#all > div', '#student > div']
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(separator=' ', strip=True)
                    if text and not text.startswith('Sentencedict.com'):
                        sentences.append(text)
            
            # Process sentences
            processed_sentences = self.process_sentences(sentences)
            
            return {
                'sentences': processed_sentences,
                'source': 'sentencedict.com'
            }
            
        except Exception as e:
            logger.error(f"Error scraping sentencedict for '{word}': {str(e)}")
            return None

    def scrape_cambridge(self, word):
        """Scrape sentences from Cambridge Dictionary"""
        try:
            url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            sentences = []
            # Cambridge uses .eg class for example sentences
            examples = soup.select('.eg')
            
            for example in examples:
                text = example.get_text(separator=' ', strip=True)
                if text:
                    sentences.append(text)
            
            processed_sentences = self.process_sentences(sentences)
            
            return {
                'sentences': processed_sentences,
                'source': 'cambridge.org'
            }
            
        except Exception as e:
            logger.error(f"Error scraping Cambridge for '{word}': {str(e)}")
            return None

    def scrape_yourdictionary(self, word):
        """Scrape sentences from YourDictionary"""
        try:
            url = f"https://sentence.yourdictionary.com/{word}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            sentences = []
            # YourDictionary uses specific classes for sentences
            sentence_elements = soup.select('.sentence-item .sentence, .example-sentence')
            
            for element in sentence_elements:
                text = element.get_text(separator=' ', strip=True)
                if text:
                    sentences.append(text)
            
            processed_sentences = self.process_sentences(sentences)
            
            return {
                'sentences': processed_sentences,
                'source': 'yourdictionary.com'
            }
            
        except Exception as e:
            logger.error(f"Error scraping YourDictionary for '{word}': {str(e)}")
            return None

    def process_sentences(self, sentences):
        """Clean and process sentences"""
        # Remove patterns like (1), (numbers), and leading numbers
        regex = re.compile(r'(\(\d+\)|\(.*?\)|\d+\.)|^\d+[\.,]|^\d+')
        processed = []
        
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            # Remove unwanted patterns and replace with space to preserve word separation
            cleaned = regex.sub(' ', sentence).strip()
            
            # Clean up multiple spaces
            cleaned = re.sub(r'\s+', ' ', cleaned)
            
            # Skip very short sentences or obvious non-sentences
            if len(cleaned) < 10 or cleaned.lower().startswith(('show all', 'random good')):
                continue
                
            processed.append(cleaned)
                
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
    
    # Get limit from query parameter, default to 20, max 50
    limit = request.args.get('limit', 20, type=int)
    limit = max(1, min(limit, 50))  # Ensure limit is between 1 and 50
    
    logger.info(f"Fetching sentences for word: {word}, limit: {limit}")
    
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
            'sources': [],
            'total_sentences': 0,
            'limit': limit
        })
    
    # Combine results
    combined_sentences = []
    sources_used = []
    
    for result in all_results:
        combined_sentences.extend(result['sentences'])
        sources_used.append(result['source'])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_sentences = []
    for sentence in combined_sentences:
        simple = sentence.lower()
        if simple not in seen and simple:
            seen.add(simple)
            unique_sentences.append(sentence)
    
    # Apply limit
    limited_sentences = unique_sentences[:limit]
    
    return jsonify({
        'word': word,
        'sentences': limited_sentences,
        'sources': list(set(sources_used)),
        'total_sentences': len(unique_sentences),
        'returned_sentences': len(limited_sentences),
        'limit': limit
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)