"""
Twitter Scraper with Accurate Metrics Extraction
-----------------------------------------------
This script accurately extracts metrics from Twitter's complex DOM structure,
including replies, retweets, likes, bookmarks, and view counts.

Requirements:
- pip install selenium beautifulsoup4 pandas flask webdriver-manager
"""

import time
import pandas as pd
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from threading import Thread

app = Flask(__name__)

# Global variables to track scraping progress
total_tweets_to_scrape = 1000
tweets_scraped = 0
is_scraping = False
scraped_data = None
error_message = None

# Helper function to parse count values with K, M suffixes
def parse_count(count_text):
    """Parse count values with K, M suffixes"""
    if not count_text or count_text.strip() == '':
        return 0
        
    # Clean the text and extract numbers
    count_text = count_text.strip().replace(',', '')
    
    # Check for K, M suffixes
    if 'K' in count_text or 'k' in count_text:
        # Remove the K and convert to thousands
        numeric_part = re.search(r'([\d\.]+)[Kk]', count_text)
        if numeric_part:
            return int(float(numeric_part.group(1)) * 1000)
    elif 'M' in count_text or 'm' in count_text:
        # Remove the M and convert to millions
        numeric_part = re.search(r'([\d\.]+)[Mm]', count_text)
        if numeric_part:
            return int(float(numeric_part.group(1)) * 1000000)
    
    # Handle plain numbers
    numeric_part = re.search(r'([\d\.]+)', count_text)
    if numeric_part:
        return int(float(numeric_part.group(1)))
    
    return 0

def extract_metrics(driver, tweet_element):
    """Extract all metrics from a tweet element using aria-label attribute when available"""
    metrics = {
        'reply_count': 0,
        'retweet_count': 0,
        'like_count': 0,
        'bookmark_count': 0,
        'view_count': 0
    }
    
    try:
        # First, try to find elements with aria-label containing all metrics at once
        # Format: "X replies, Y reposts, Z likes, A bookmarks, B views"
        elements_with_aria_label = tweet_element.find_elements(By.CSS_SELECTOR, '[aria-label]')
        
        for element in elements_with_aria_label:
            aria_label = element.get_attribute('aria-label')
            if not aria_label:
                continue
                
            # Check if this aria-label contains multiple metrics
            if ('replies' in aria_label and 'likes' in aria_label) or 'views' in aria_label:
                print(f"Found metrics aria-label: {aria_label}")
                
                # Extract each metric from the aria-label
                reply_match = re.search(r'(\d+(?:,\d+)*)\s+replies', aria_label)
                if reply_match:
                    metrics['reply_count'] = parse_count(reply_match.group(1))
                
                # Twitter might use "reposts" or "retweets"
                repost_match = re.search(r'(\d+(?:,\d+)*)\s+(?:reposts|retweets)', aria_label)
                if repost_match:
                    metrics['retweet_count'] = parse_count(repost_match.group(1))
                
                like_match = re.search(r'(\d+(?:,\d+)*)\s+likes', aria_label)
                if like_match:
                    metrics['like_count'] = parse_count(like_match.group(1))
                
                bookmark_match = re.search(r'(\d+(?:,\d+)*)\s+bookmarks', aria_label)
                if bookmark_match:
                    metrics['bookmark_count'] = parse_count(bookmark_match.group(1))
                
                view_match = re.search(r'(\d+(?:,\d+)*)\s+views', aria_label)
                if view_match:
                    metrics['view_count'] = parse_count(view_match.group(1))
                
                # If we found most of the metrics, we can probably stop looking
                if sum(1 for v in metrics.values() if v > 0) >= 3:
                    break
        
        # If we couldn't find all metrics using the comprehensive aria-label,
        # look for individual metric aria-labels
        for metric_type, patterns in [
            ('reply_count', [r'(\d+(?:,\d+)*)\s+(?:reply|replies)']),
            ('retweet_count', [r'(\d+(?:,\d+)*)\s+(?:repost|reposts|retweet|retweets)']),
            ('like_count', [r'(\d+(?:,\d+)*)\s+like', r'(\d+(?:,\d+)*)\s+likes']),
            ('bookmark_count', [r'(\d+(?:,\d+)*)\s+bookmark', r'(\d+(?:,\d+)*)\s+bookmarks']),
            ('view_count', [r'(\d+(?:,\d+)*)\s+view', r'(\d+(?:,\d+)*)\s+views'])
        ]:
            if metrics[metric_type] == 0:  # Only look if we haven't found this metric yet
                # Try to find elements specific to this metric type
                selector = f'[data-testid="{metric_type.split("_")[0]}"]'
                try:
                    metric_elements = tweet_element.find_elements(By.CSS_SELECTOR, selector)
                    for metric_element in metric_elements:
                        aria_label = metric_element.get_attribute('aria-label')
                        if not aria_label:
                            continue
                            
                        # Try each pattern for this metric
                        for pattern in patterns:
                            match = re.search(pattern, aria_label)
                            if match:
                                metrics[metric_type] = parse_count(match.group(1))
                                break
                        
                        if metrics[metric_type] > 0:
                            break
                except:
                    pass
        
        # If we still couldn't find all metrics, try using JavaScript for a more thorough search
        if any(value == 0 for value in metrics.values()):
            script = """
            function findAllAriaLabels(element) {
                const allAriaLabels = [];
                const elements = element.querySelectorAll('[aria-label]');
                for (const el of elements) {
                    const label = el.getAttribute('aria-label');
                    if (label) allAriaLabels.push(label);
                }
                return allAriaLabels;
            }
            return findAllAriaLabels(arguments[0]);
            """
            
            aria_labels = driver.execute_script(script, tweet_element)
            
            for aria_label in aria_labels:
                # Try to extract any missing metrics
                if metrics['reply_count'] == 0:
                    match = re.search(r'(\d+(?:,\d+)*)\s+(?:reply|replies)', aria_label)
                    if match:
                        metrics['reply_count'] = parse_count(match.group(1))
                
                if metrics['retweet_count'] == 0:
                    match = re.search(r'(\d+(?:,\d+)*)\s+(?:repost|reposts|retweet|retweets)', aria_label)
                    if match:
                        metrics['retweet_count'] = parse_count(match.group(1))
                
                if metrics['like_count'] == 0:
                    match = re.search(r'(\d+(?:,\d+)*)\s+like', aria_label)
                    if match:
                        metrics['like_count'] = parse_count(match.group(1))
                
                if metrics['bookmark_count'] == 0:
                    match = re.search(r'(\d+(?:,\d+)*)\s+bookmark', aria_label)
                    if match:
                        metrics['bookmark_count'] = parse_count(match.group(1))
                
                if metrics['view_count'] == 0:
                    match = re.search(r'(\d+(?:,\d+)*)\s+view', aria_label)
                    if match:
                        metrics['view_count'] = parse_count(match.group(1))
        
    except Exception as e:
        print(f"Error extracting metrics from aria-labels: {str(e)}")
    
    # Ensure all metrics are integers
    for key in metrics:
        if isinstance(metrics[key], float):
            metrics[key] = int(metrics[key])
        elif not isinstance(metrics[key], int):
            metrics[key] = 0
            
    return metrics
    
    try:
        # Use JavaScript to extract metrics - more reliable for complex DOM
        script = """
        function extractMetrics(element) {
            const metrics = {
                reply_count: 0,
                retweet_count: 0,
                like_count: 0,
                bookmark_count: 0,
                view_count: 0
            };
            
            // Helper to extract number from text
            function extractNumber(text) {
                if (!text) return 0;
                text = text.trim();
                
                // Handle K and M suffixes
                if (text.includes('K') || text.includes('k')) {
                    return parseFloat(text.replace(/[Kk]/, '')) * 1000;
                } else if (text.includes('M') || text.includes('m')) {
                    return parseFloat(text.replace(/[Mm]/, '')) * 1000000;
                }
                
                // Extract any number
                const match = text.match(/\\d+(?:\\.\\d+)?/);
                return match ? parseFloat(match[0]) : 0;
            }
            
            // Extract reply count
            try {
                const replyElement = element.querySelector('[data-testid="reply"]');
                if (replyElement) {
                    const spans = replyElement.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent.trim();
                        if (/^\\d|[Kk]|[Mm]/.test(text)) {
                            metrics.reply_count = extractNumber(text);
                            break;
                        }
                    }
                }
            } catch (e) {}
            
            // Extract retweet count
            try {
                const retweetElement = element.querySelector('[data-testid="retweet"]');
                if (retweetElement) {
                    const spans = retweetElement.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent.trim();
                        if (/^\\d|[Kk]|[Mm]/.test(text)) {
                            metrics.retweet_count = extractNumber(text);
                            break;
                        }
                    }
                }
            } catch (e) {}
            
            // Extract like count
            try {
                const likeElement = element.querySelector('[data-testid="like"]');
                if (likeElement) {
                    const spans = likeElement.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent.trim();
                        if (/^\\d|[Kk]|[Mm]/.test(text)) {
                            metrics.like_count = extractNumber(text);
                            break;
                        }
                    }
                }
            } catch (e) {}
            
            // Extract bookmark count
            try {
                const bookmarkElement = element.querySelector('[data-testid="bookmark"]');
                if (bookmarkElement) {
                    const spans = bookmarkElement.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent.trim();
                        if (/^\\d|[Kk]|[Mm]/.test(text)) {
                            metrics.bookmark_count = extractNumber(text);
                            break;
                        }
                    }
                }
            } catch (e) {}
            
            // Extract view count - look for text containing "Views"
            try {
                const viewElements = Array.from(element.querySelectorAll('*')).filter(el => 
                    el.textContent.includes('Views'));
                    
                for (const viewEl of viewElements) {
                    // Look for a nearby number
                    const parent = viewEl.parentElement;
                    if (parent) {
                        const allText = parent.textContent;
                        const match = allText.match(/(\\d+(?:\\.\\d+)?[KkMm]?)\\s*Views/);
                        if (match) {
                            metrics.view_count = extractNumber(match[1]);
                            break;
                        }
                    }
                }
                
                // If still no view count, try a more direct approach
                if (metrics.view_count === 0) {
                    const transitionContainers = element.querySelectorAll('[data-testid="app-text-transition-container"]');
                    for (const container of transitionContainers) {
                        const text = container.textContent.trim();
                        if (/^\\d|[Kk]|[Mm]/.test(text)) {
                            // Check if this container is near "Views"
                            let parent = container.parentElement;
                            for (let i = 0; i < 5 && parent; i++) {
                                if (parent.textContent.includes('Views')) {
                                    metrics.view_count = extractNumber(text);
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            if (metrics.view_count > 0) break;
                        }
                    }
                }
            } catch (e) {}
            
            return metrics;
        }
        
        return extractMetrics(arguments[0]);
        """
        
        # Execute the JavaScript to extract metrics
        extracted_metrics = driver.execute_script(script, tweet_element)
        
        # Update our metrics with the JavaScript results
        if extracted_metrics:
            metrics.update(extracted_metrics)
        
    except Exception as e:
        print(f"Error extracting metrics with JavaScript: {str(e)}")
        
        # Fallback to more traditional methods if JavaScript fails
        try:
            # Extract metrics using Selenium directly
            
            # Reply count
            try:
                reply_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
                reply_text = reply_element.text
                if reply_text:
                    numbers = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?[KkMm]?)', reply_text)
                    if numbers:
                        metrics['reply_count'] = parse_count(numbers[0])
            except:
                pass
                
            # Retweet count
            try:
                retweet_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="retweet"]')
                retweet_text = retweet_element.text
                if retweet_text:
                    numbers = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?[KkMm]?)', retweet_text)
                    if numbers:
                        metrics['retweet_count'] = parse_count(numbers[0])
            except:
                pass
                
            # Like count
            try:
                like_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
                like_text = like_element.text
                if like_text:
                    numbers = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?[KkMm]?)', like_text)
                    if numbers:
                        metrics['like_count'] = parse_count(numbers[0])
            except:
                pass
                
            # Bookmark count
            try:
                bookmark_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="bookmark"]')
                bookmark_text = bookmark_element.text
                if bookmark_text:
                    numbers = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?[KkMm]?)', bookmark_text)
                    if numbers:
                        metrics['bookmark_count'] = parse_count(numbers[0])
            except:
                pass
                
            # View count - look for text containing "Views"
            try:
                # Get the HTML and search for the pattern
                html = tweet_element.get_attribute('outerHTML')
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for spans with "Views" text
                view_spans = soup.find_all(string=lambda text: text and "Views" in text)
                for span in view_spans:
                    # Go up the tree to find a parent with a number
                    parent = span.parent
                    for _ in range(5):  # Check up to 5 levels
                        if not parent:
                            break
                        parent_text = parent.get_text()
                        # Extract numbers followed by "Views"
                        matches = re.findall(r'([\d,.]+[KkMm]?)\s*Views', parent_text)
                        if matches:
                            metrics['view_count'] = parse_count(matches[0])
                            break
                        parent = parent.parent
            except:
                pass
                
        except Exception as e:
            print(f"Error in fallback metrics extraction: {str(e)}")
    
    # Ensure all metrics are integers
    for key in metrics:
        if isinstance(metrics[key], float):
            metrics[key] = int(metrics[key])
        elif not isinstance(metrics[key], int):
            metrics[key] = 0
            
    return metrics

def extract_username(url):
    """Extract username from URL or handle direct username input"""
    url = url.strip().lower()
    
    # Try to match various Twitter URL patterns
    patterns = [
        r'(?:twitter\.com|x\.com)/([^/\?]+)',  # Standard URL
        r'@([a-zA-Z0-9_]+)',                   # @username format
        r'^([a-zA-Z0-9_]+)$'                   # Just the username
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            username = match.group(1)
            # Clean up the username
            if username.startswith('@'):
                username = username[1:]
            # Skip if it's a Twitter reserved word/path
            if username in ['home', 'explore', 'notifications', 'messages', 'search']:
                continue
            return username
    
    return None

# Add these modifications to your existing code

def setup_driver():
    """Set up and return a configured Chrome webdriver with improved settings for small accounts"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # More realistic user agent
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Add these options to help with small accounts
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute CDP commands to prevent detection
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
    })
    
    return driver

def scrape_tweets(username):
    global tweets_scraped, is_scraping, scraped_data, error_message
    
    driver = None
    
    try:
        tweets_scraped = 0
        is_scraping = True
        error_message = None
        tweets_list = []
        
        driver = setup_driver()
        profile_url = f"https://twitter.com/{username}"
        driver.get(profile_url)
        
        # Wait for the profile to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="primaryColumn"]'))
        )
        
        # Define a helper function to check for tweet presence
        def tweet_is_present(driver):
            return (
                len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')) > 0 or
                len(driver.find_elements(By.CSS_SELECTOR, 'article[role="article"]')) > 0 or
                len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweetText"]')) > 0
            )
        
        # Try multiple scrolls to load tweets
        max_attempts = 3  # Number of scroll attempts
        wait_time = 5     # Seconds to wait after each scroll
        
        for attempt in range(max_attempts):
            if tweet_is_present(driver):
                break  # Tweets found, proceed to scraping
            # Scroll to the bottom of the page
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(wait_time)  # Wait for content to load
        else:
            # After all attempts, check for specific conditions
            if "This account doesn't exist" in driver.page_source:
                error_message = f"The account @{username} doesn't exist."
            elif "Account suspended" in driver.page_source:
                error_message = f"The account @{username} has been suspended."
            elif "These Tweets are protected" in driver.page_source:
                error_message = f"The account @{username} is private/protected."
            elif "This account hasn't Tweeted" in driver.page_source:
                error_message = f"The account @{username} exists but has no tweets."
            else:
                error_message = f"Could not find tweets for @{username} after multiple attempts."
            is_scraping = False
            return
        
        # If we made it here but have an error message, return
        if error_message:
            is_scraping = False
            return
        
        # Proceed with the main scraping loop (rest of your existing code)
        last_tweets = set()
        tweet_selectors = [
            '[data-testid="tweet"]',
            'article[role="article"]',
            'div[data-testid="cellInnerDiv"]'
        ]
        consecutive_empty_scrolls = 0
        max_empty_scrolls = 5
        
        while tweets_scraped < total_tweets_to_scrape and consecutive_empty_scrolls < max_empty_scrolls:
            tweet_elements = []
            for selector in tweet_selectors:
                tweet_elements.extend(driver.find_elements(By.CSS_SELECTOR, selector))
            
            new_tweets_found = False
            for tweet_element in tweet_elements:
                try:
                    status_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    if not status_links:
                        continue
                    tweet_url = status_links[0].get_attribute('href')
                    if tweet_url in last_tweets:
                        continue
                    last_tweets.add(tweet_url)
                    new_tweets_found = True
                    tweet_data = extract_tweet_data(driver, tweet_element)
                    if tweet_data:
                        tweets_list.append(tweet_data)
                        tweets_scraped += 1
                        if tweets_scraped >= total_tweets_to_scrape:
                            break
                except Exception as e:
                    print(f"Error processing tweet: {str(e)}")
                    continue
            
            if tweets_scraped >= total_tweets_to_scrape:
                break
            
            if not new_tweets_found:
                consecutive_empty_scrolls += 1
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
            else:
                consecutive_empty_scrolls = 0
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
        
        if tweets_list:
            tweets_df = pd.DataFrame(tweets_list)
            tweets_df = tweets_df.sort_values(by='engagement_score', ascending=False)
            scraped_data = tweets_df.head(20).to_dict('records')  # Top 20 tweets
        else:
            scraped_data = []
            if not error_message:
                error_message = f"No tweets found for @{username}."
            
    except Exception as e:
        error_message = f"Error occurred: {str(e)}"
        scraped_data = []
    finally:
        is_scraping = False
        if driver:
            driver.quit()
            
    """Modified main function with improved handling for small accounts"""
    global tweets_scraped, is_scraping, scraped_data, error_message
    
    driver = None
    
    try:
        tweets_scraped = 0
        is_scraping = True
        error_message = None
        tweets_list = []
        
        # Initialize the driver
        driver = setup_driver()
        
        # Navigate to the user's profile
        profile_url = f"https://twitter.com/{username}"
        driver.get(profile_url)
        
        # Give more time for small accounts to load (increase timeout)
        try:
            # First check if we're on a valid profile page by looking for profile elements
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="primaryColumn"]'))
            )
            
            # Try multiple possible tweet selectors with a longer timeout
            try:
                # Try the standard tweet selector
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweet"]'))
                )
            except TimeoutException:
                # Also try alternative selectors for tweets
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'article[role="article"]'))
                    )
                except TimeoutException:
                    # One more attempt with a different selector
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetText"]'))
                        )
                    except TimeoutException:
                        # If we found a profile but no tweets, check if account has no tweets
                        if "This account hasn't Tweeted" in driver.page_source or "This account hasn't posted" in driver.page_source:
                            error_message = f"The account @{username} exists but has no tweets."
                        else:
                            # Sometimes we need to scroll a bit to load tweets for small accounts
                            driver.execute_script("window.scrollTo(0, 300);")
                            time.sleep(3)  # Wait longer for content to load after scrolling
                            
                            # Check if tweets loaded after scrolling
                            if len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')) == 0 and \
                               len(driver.find_elements(By.CSS_SELECTOR, 'article[role="article"]')) == 0:
                                error_message = f"Could not find tweets for @{username}. The profile may have very few tweets or Twitter's layout has changed."
        except TimeoutException:
            # Check if account doesn't exist
            if "This account doesn't exist" in driver.page_source:
                error_message = f"The account @{username} doesn't exist."
            # Check if account is suspended
            elif "Account suspended" in driver.page_source:
                error_message = f"The account @{username} has been suspended."
            # Check if account is private
            elif "These Tweets are protected" in driver.page_source:
                error_message = f"The account @{username} is private/protected."
            else:
                error_message = f"Could not load profile for @{username}. Twitter may be experiencing issues or blocking the request."
            
            is_scraping = False
            return
        
        # If we made it here but have an error message, return
        if error_message:
            is_scraping = False
            return
        
        # Keep track of the last tweet we've seen to avoid duplicates
        last_tweets = set()
        
        # For small accounts, we'll use multiple selectors to find tweets
        tweet_selectors = [
            '[data-testid="tweet"]',
            'article[role="article"]',
            'div[data-testid="cellInnerDiv"]'
        ]
        
        # Scroll and collect tweets until we reach the limit
        consecutive_empty_scrolls = 0
        max_empty_scrolls = 5  # Allow more empty scrolls for small accounts
        
        while tweets_scraped < total_tweets_to_scrape and consecutive_empty_scrolls < max_empty_scrolls:
            # Find all visible tweets using multiple selectors
            tweet_elements = []
            for selector in tweet_selectors:
                tweet_elements.extend(driver.find_elements(By.CSS_SELECTOR, selector))
            
            # Process new tweets
            new_tweets_found = False
            for tweet_element in tweet_elements:
                # Get a unique identifier for this tweet
                try:
                    # Try to find a status link (tweet URL)
                    status_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    
                    if not status_links:
                        # Skip elements that don't contain a tweet URL
                        continue
                    
                    tweet_url = status_links[0].get_attribute('href')
                    if tweet_url in last_tweets:
                        continue
                    
                    last_tweets.add(tweet_url)
                    new_tweets_found = True
                    
                    # Extract tweet data
                    tweet_data = extract_tweet_data(driver, tweet_element)
                    if tweet_data:
                        tweets_list.append(tweet_data)
                        tweets_scraped += 1
                        
                        # Check if we've reached the limit
                        if tweets_scraped >= total_tweets_to_scrape:
                            break
                except Exception as e:
                    print(f"Error processing tweet: {str(e)}")
                    continue
            
            # If we've reached the limit, break
            if tweets_scraped >= total_tweets_to_scrape:
                break
            
            # If no new tweets were found, increment our counter
            if not new_tweets_found:
                consecutive_empty_scrolls += 1
                
                # Try scrolling a bit more
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)  # Longer wait for small accounts
            else:
                # Reset counter since we found tweets
                consecutive_empty_scrolls = 0
                
                # Scroll down to load more tweets
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Slightly longer wait between scrolls
        
        # Process results
        if tweets_list:
            # Create DataFrame and sort by engagement
            tweets_df = pd.DataFrame(tweets_list)
            tweets_df = tweets_df.sort_values(by='engagement_score', ascending=False)
            scraped_data = tweets_df.head(20).to_dict('records')
        else:
            scraped_data = []
            if not error_message:  # Only set if not already set
                error_message = f"No tweets found for @{username}. The profile may have very few or no public tweets."
            
    except Exception as e:
        error_message = f"Error occurred: {str(e)}"
        scraped_data = []
    finally:
        is_scraping = False
        if driver:
            driver.quit()

# Modified extract_tweet_data function to better handle small accounts
def extract_tweet_data(driver, tweet_element):
    """Extract all data from a tweet element with improved handling for small accounts"""
    try:
        # Extract content - try multiple selectors
        content = "No text content"
        try:
            # Try standard selector
            content_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
            content = content_element.text
        except NoSuchElementException:
            try:
                # Try alternative selector
                content_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[lang]')
                content = content_element.text
            except NoSuchElementException:
                pass
        
        # Extract user - try multiple approaches
        user = "Unknown user"
        try:
            user_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
            user_spans = user_element.find_elements(By.TAG_NAME, 'span')
            if user_spans:
                user = user_spans[0].text
        except NoSuchElementException:
            try:
                # Alternative approach
                user_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[role="link"] div[dir="ltr"]')
                if user_links:
                    user = user_links[0].text
            except:
                pass
        
        # Extract timestamp
        timestamp = None
        try:
            timestamp_element = tweet_element.find_element(By.CSS_SELECTOR, "time")
            timestamp = timestamp_element.get_attribute("datetime")
        except NoSuchElementException:
            # Try to extract date from the URL if timestamp element not found
            try:
                url_element = tweet_element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                url = url_element.get_attribute('href')
                # Sometimes we can find a date span near the URL
                parent = url_element.find_element(By.XPATH, './..')
                time_spans = parent.find_elements(By.TAG_NAME, 'span')
                for span in time_spans:
                    # Look for text that might be a date (e.g., "Apr 5" or "2h")
                    if re.match(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d+[hmd])', span.text):
                        # We found something that looks like a date reference
                        timestamp = span.text
                        break
            except:
                pass
        
        # Extract tweet URL
        url = ""
        try:
            url_element = tweet_element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
            url = url_element.get_attribute('href')
        except NoSuchElementException:
            pass
        
        # Extract tweet ID from URL
        tweet_id = "unknown"
        if url:
            match = re.search(r'/status/(\d+)', url)
            if match:
                tweet_id = match.group(1)
        
        # Extract all metrics
        metrics = extract_metrics(driver, tweet_element)
        
        # Calculate engagement score
        base_engagement = (metrics['reply_count'] * 3) + (metrics['retweet_count'] * 2) + metrics['like_count'] + (metrics['bookmark_count'] * 1.5)
        
        if metrics['view_count'] > 0:
            impression_factor = 1 + (metrics['view_count'] / 10000)
            engagement_score = base_engagement * impression_factor
        else:
            engagement_score = base_engagement
            
        engagement_score = round(engagement_score)
        
        return {
            'id': tweet_id,
            'date': timestamp,
            'content': content,
            'user': user.replace('@', ''),
            'url': url,
            'reply_count': metrics['reply_count'],
            'retweet_count': metrics['retweet_count'],
            'like_count': metrics['like_count'],
            'bookmark_count': metrics['bookmark_count'],
            'view_count': metrics['view_count'],
            'engagement_score': engagement_score
        }
    except Exception as e:
        print(f"Error extracting tweet data: {str(e)}")
        return None
    """Extract all data from a tweet element"""
    try:
        # Extract content
        try:
            content = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
        except NoSuchElementException:
            content = "No text content"
        
        # Extract user
        try:
            user_element = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
            user = user_element.find_element(By.CSS_SELECTOR, 'span').text
        except NoSuchElementException:
            user = "Unknown user"
        
        # Extract timestamp
        try:
            timestamp_element = tweet_element.find_element(By.CSS_SELECTOR, "time")
            timestamp = timestamp_element.get_attribute("datetime")
        except NoSuchElementException:
            timestamp = None
        
        # Extract tweet URL
        try:
            url = tweet_element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]').get_attribute('href')
        except NoSuchElementException:
            url = ""
        
        # Extract tweet ID from URL
        try:
            tweet_id = re.search(r'/status/(\d+)', url).group(1)
        except (AttributeError, IndexError):
            tweet_id = "unknown"
        
        # Extract all metrics
        metrics = extract_metrics(driver, tweet_element)
        
        # Calculate engagement score - now including bookmarks
        # Formula: (replies*3 + retweets*2 + likes + bookmarks*1.5) * (1 + impressions/10000)
        base_engagement = (metrics['reply_count'] * 3) + (metrics['retweet_count'] * 2) + metrics['like_count'] + (metrics['bookmark_count'] * 1.5)
        
        # If we have view count, factor it in
        if metrics['view_count'] > 0:
            impression_factor = 1 + (metrics['view_count'] / 10000)
            engagement_score = base_engagement * impression_factor
        else:
            engagement_score = base_engagement
            
        # Round to a whole number
        engagement_score = round(engagement_score)
        
        return {
            'id': tweet_id,
            'date': timestamp,
            'content': content,
            'user': user.replace('@', ''),
            'url': url,
            'reply_count': metrics['reply_count'],
            'retweet_count': metrics['retweet_count'],
            'like_count': metrics['like_count'],
            'bookmark_count': metrics['bookmark_count'],
            'view_count': metrics['view_count'],
            'engagement_score': engagement_score
        }
    except Exception as e:
        print(f"Error extracting tweet data: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def start_scraping():
    global tweets_scraped, is_scraping, scraped_data, error_message
    
    if is_scraping:
        return jsonify({'error': 'Already scraping tweets. Please wait.'})
    
    profile_url = request.json.get('profile_url', '')
    username = extract_username(profile_url)
    
    if not username:
        return jsonify({
            'error': 'Invalid profile URL or username format. Please enter a valid Twitter/X profile URL (e.g., https://twitter.com/username or https://x.com/username) or just the username.'
        })
    
    # Validate username format (basic check)
    if not re.match(r'^[a-zA-Z0-9_]{1,15}$', username):
        return jsonify({
            'error': 'Invalid Twitter username format. Twitter usernames can only contain letters, numbers, and underscores, and must be 15 characters or less.'
        })
    
    # Reset variables
    tweets_scraped = 0
    scraped_data = None
    error_message = None
    
    # Start scraping in a separate thread
    thread = Thread(target=scrape_tweets, args=(username,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'message': f'Started scraping tweets for @{username}. This may take a few minutes depending on the account activity.'
    })

@app.route('/progress')
def get_progress():
    return jsonify({
        'is_scraping': is_scraping,
        'data': scraped_data,
        'error': error_message
    })

if __name__ == '__main__':
    app.run(debug=True)