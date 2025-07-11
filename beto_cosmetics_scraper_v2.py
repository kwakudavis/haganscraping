#!/usr/bin/env python3
"""
Beto Cosmetics Product Scraper v2

Enhanced scraper that uses Shopify JSON API for efficient product discovery
and comprehensive data extraction from https://betocosmetics.com/

Author: Data Quality Analyst
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import logging
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraping.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class BetoCosmeticsScraperV2:
    """
    Enhanced scraper for Beto Cosmetics that uses Shopify JSON API
    for efficient product discovery and extraction.
    """
    
    def __init__(self, base_url: str = "https://betocosmetics.com", delay: float = 1.0):
        """
        Initialize the scraper.
        
        Args:
            base_url: Base URL of the website
            delay: Delay between requests in seconds
        """
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        
        # Set user agent to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        self.products_data = []
        self.failed_urls = []
    
    def get_products_from_json_api(self, limit: int = 250) -> List[Dict]:
        """
        Get products from Shopify JSON API.
        
        Args:
            limit: Maximum number of products to fetch (Shopify limit is 250 per page)
            
        Returns:
            List of product data from API
        """
        logger.info("Fetching products from Shopify JSON API")
        
        all_products = []
        page = 1
        
        while len(all_products) < limit:
            try:
                # Shopify API URL with pagination
                api_url = f"{self.base_url}/products.json"
                params = {
                    'limit': min(250, limit - len(all_products)),  # Shopify max is 250
                    'page': page
                }
                
                logger.info(f"Fetching page {page} from API: {api_url}")
                response = self.session.get(api_url, params=params, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                products = data.get('products', [])
                
                if not products:
                    logger.info("No more products found, stopping pagination")
                    break
                
                all_products.extend(products)
                logger.info(f"Fetched {len(products)} products from page {page}, total: {len(all_products)}")
                
                page += 1
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"Error fetching products from API page {page}: {e}")
                break
        
        logger.info(f"Total products fetched from API: {len(all_products)}")
        return all_products[:limit]
    
    def get_additional_product_data(self, product_url: str) -> Dict:
        """
        Get additional product data by scraping the product page.
        This supplements the JSON API data with information not available in the API.
        
        Args:
            product_url: URL of the product page
            
        Returns:
            Dictionary with additional product data
        """
        logger.debug(f"Fetching additional data from: {product_url}")
        
        additional_data = {}
        
        try:
            response = self.session.get(product_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract ingredients (often not in JSON API)
            ingredient_selectors = [
                '.ingredients', '.product-ingredients', '[data-ingredients]',
                'div:contains("Ingredients")', 'div:contains("INGREDIENTS")',
                'p:contains("Ingredients")', 'span:contains("Ingredients")',
                '.product-description'
            ]
            
            for selector in ingredient_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    # Look for ingredient lists (usually containing commas and specific keywords)
                    if (',' in text and len(text) > 50 and 
                        any(word in text.lower() for word in ['acid', 'oil', 'extract', 'vitamin', 'glycerin', 'water'])):
                        # Clean up the ingredients text
                        ingredients_text = re.sub(r'^.*?ingredients?\s*:?\s*', '', text, flags=re.IGNORECASE)
                        additional_data['ingredients'] = ingredients_text.strip()
                        break
                
                if additional_data.get('ingredients'):
                    break
            
            # Extract barcode/EAN/UPC (often not in JSON API)
            barcode_selectors = [
                '.barcode', '.ean', '.upc', '[data-barcode]',
                'span:contains("EAN")', 'span:contains("UPC")', 'span:contains("Barcode")'
            ]
            for selector in barcode_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(strip=True)
                    barcode_match = re.search(r'\b\d{8,13}\b', text)
                    if barcode_match:
                        additional_data['barcode_ean_upc'] = barcode_match.group(0)
                        break
            
            # Extract product line/collection (sometimes available on page)
            line_selectors = [
                '.product-line', '.collection', '.product-collection',
                '[data-collection]', '.product-type', '.breadcrumb'
            ]
            for selector in line_selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    line_text = element.get_text(strip=True)
                    if line_text and line_text.lower() not in ['home', 'products', 'shop']:
                        additional_data['product_line_name'] = line_text
                        break
            
            time.sleep(self.delay)
            
        except Exception as e:
            logger.warning(f"Failed to get additional data from {product_url}: {e}")
            self.failed_urls.append(product_url)
        
        return additional_data
    
    def process_shopify_product(self, product_json: Dict, fetch_additional: bool = True) -> Dict:
        """
        Process a product from Shopify JSON API into our standard format.
        
        Args:
            product_json: Product data from Shopify JSON API
            fetch_additional: Whether to fetch additional data from product page
            
        Returns:
            Processed product data dictionary
        """
        try:
            # Extract basic product information
            product_data = {
                'website_name': 'Beto Cosmetics',
                'product_id_sku': '',
                'product_name': product_json.get('title', '').strip(),
                'brand_name': product_json.get('vendor', '').strip(),
                'product_line_name': '',
                'product_description': BeautifulSoup(product_json.get('body_html', ''), 'html.parser').get_text(strip=True),
                'product_image_url': '',
                'barcode_ean_upc': '',
                'ingredients': '',
                'price': '',
                'product_url': f"{self.base_url}/products/{product_json.get('handle', '')}"
            }
            
            # Extract SKU from variants (Shopify products have variants)
            variants = product_json.get('variants', [])
            if variants:
                first_variant = variants[0]
                product_data['product_id_sku'] = first_variant.get('sku', '').strip()
                
                # Extract price from first variant
                price = first_variant.get('price')
                if price:
                    # Shopify API returns price as string without currency
                    # Need to determine currency - usually from the variant or site settings
                    compare_at_price = first_variant.get('compare_at_price')
                    if compare_at_price and float(compare_at_price) > float(price):
                        product_data['price'] = f"BD {price} (was BD {compare_at_price})"
                    else:
                        product_data['price'] = f"BD {price}"  # Assuming BD (Bahraini Dinar) based on example
                
                # Extract barcode from variant
                barcode = first_variant.get('barcode', '').strip()
                if barcode:
                    product_data['barcode_ean_upc'] = barcode
            
            # Extract main product image
            images = product_json.get('images', [])
            if images:
                # Get the first (main) image
                main_image = images[0]
                image_src = main_image.get('src', '')
                if image_src:
                    # Ensure it's a full URL
                    if image_src.startswith('//'):
                        image_src = 'https:' + image_src
                    elif image_src.startswith('/'):
                        image_src = self.base_url + image_src
                    product_data['product_image_url'] = image_src
            
            # Extract product type/tags as potential product line
            product_type = product_json.get('product_type', '').strip()
            if product_type:
                product_data['product_line_name'] = product_type
            
            # Try to extract ingredients from description if not found elsewhere
            description = product_data['product_description']
            if description:
                # Look for ingredients in description
                ingredients_match = re.search(r'ingredients?\s*:?\s*([^.]+)', description, re.IGNORECASE)
                if ingredients_match:
                    ingredients_text = ingredients_match.group(1).strip()
                    if len(ingredients_text) > 30 and ',' in ingredients_text:
                        product_data['ingredients'] = ingredients_text
            
            # Fetch additional data from product page if requested
            if fetch_additional and product_data['product_url']:
                additional_data = self.get_additional_product_data(product_data['product_url'])
                
                # Update with additional data (only if not already found)
                for key, value in additional_data.items():
                    if value and not product_data.get(key):
                        product_data[key] = value
            
            logger.info(f"Processed product: {product_data['product_name']}")
            return product_data
            
        except Exception as e:
            logger.error(f"Error processing product {product_json.get('title', 'Unknown')}: {e}")
            return None
    
    def scrape_products(self, min_products: int = 10, fetch_additional: bool = True) -> List[Dict]:
        """
        Main method to scrape products from Beto Cosmetics using Shopify API.
        
        Args:
            min_products: Minimum number of products to scrape
            fetch_additional: Whether to fetch additional data from product pages
            
        Returns:
            List of product dictionaries
        """
        logger.info(f"Starting scrape for minimum {min_products} products")
        
        # Get products from Shopify JSON API
        api_products = self.get_products_from_json_api(limit=min_products + 5)  # Get a few extra
        
        if not api_products:
            logger.error("No products found in JSON API")
            return []
        
        # Process each product
        for i, product_json in enumerate(api_products, 1):
            logger.info(f"Processing product {i}/{len(api_products)}")
            
            product_data = self.process_shopify_product(product_json, fetch_additional=fetch_additional)
            if product_data:
                self.products_data.append(product_data)
            
            # Stop if we have enough products
            if len(self.products_data) >= min_products:
                break
        
        logger.info(f"Successfully scraped {len(self.products_data)} products")
        
        if self.failed_urls:
            logger.warning(f"Failed to get additional data from {len(self.failed_urls)} URLs")
        
        return self.products_data
    
    def save_to_csv(self, filename: str = "beto_cosmetics_products_v2.csv") -> None:
        """Save scraped data to CSV file."""
        if not self.products_data:
            logger.error("No data to save")
            return
        
        df = pd.DataFrame(self.products_data)
        
        # Reorder columns to match requirements
        column_order = [
            'product_id_sku', 'product_line_name', 'brand_name', 'product_name',
            'product_image_url', 'barcode_ean_upc', 'ingredients', 'price', 'website_name'
        ]
        
        # Include only columns that exist in the data
        available_columns = [col for col in column_order if col in df.columns]
        df = df[available_columns]
        
        df.to_csv(filename, index=False)
        logger.info(f"Data saved to {filename}")


def analyze_ingredient_overlap(products_data: List[Dict]) -> pd.DataFrame:
    """
    Analyze ingredient overlap between products.
    
    Args:
        products_data: List of product dictionaries
        
    Returns:
        DataFrame with ingredient overlap analysis
    """
    logger.info("Analyzing ingredient overlap")
    
    # Parse ingredients for each product
    product_ingredients = {}
    
    for product in products_data:
        product_name = product.get('product_name', 'Unknown')
        ingredients_text = product.get('ingredients', '')
        
        if ingredients_text:
            # Split ingredients by comma and clean them
            ingredients = [
                ingredient.strip().lower()
                for ingredient in re.split(r'[,;]', ingredients_text)
                if ingredient.strip()
            ]
            product_ingredients[product_name] = set(ingredients)
    
    # Find products with shared ingredients
    overlap_results = []
    group_counter = 1
    
    products_list = list(product_ingredients.keys())
    for i, product1 in enumerate(products_list):
        for product2 in products_list[i+1:]:
            ingredients1 = product_ingredients[product1]
            ingredients2 = product_ingredients[product2]
            
            shared = ingredients1.intersection(ingredients2)
            
            if len(shared) >= 2:  # Products sharing 2+ ingredients
                overlap_results.append({
                    'product_1': product1,
                    'product_2': product2,
                    'shared_ingredients_count': len(shared),
                    'shared_ingredients': ', '.join(sorted(shared)),
                    'ingredient_group': f"Group_{group_counter}"
                })
                group_counter += 1
    
    if overlap_results:
        df_overlap = pd.DataFrame(overlap_results)
        logger.info(f"Found {len(overlap_results)} product pairs with 2+ shared ingredients")
        return df_overlap
    else:
        logger.info("No products found with 2+ shared ingredients")
        return pd.DataFrame()


def main():
    """Main execution function."""
    logger.info("Starting Beto Cosmetics scraper v2")
    
    try:
        # Initialize scraper
        scraper = BetoCosmeticsScraperV2(delay=1.0)  # Faster since we're using API
        
        # Scrape products
        products = scraper.scrape_products(min_products=10, fetch_additional=True)
        
        if not products:
            logger.error("No products were scraped successfully")
            return
        
        # Save raw data
        scraper.save_to_csv("beto_cosmetics_products_v2.csv")
        
        # Analyze ingredient overlap
        ingredient_analysis = analyze_ingredient_overlap(products)
        
        if not ingredient_analysis.empty:
            ingredient_analysis.to_csv("ingredient_overlap_analysis_v2.csv", index=False)
            logger.info("Ingredient overlap analysis saved to ingredient_overlap_analysis_v2.csv")
        
        # Print summary
        logger.info(f"\n=== SCRAPING SUMMARY ===")
        logger.info(f"Total products scraped: {len(products)}")
        logger.info(f"Products with ingredients: {sum(1 for p in products if p.get('ingredients'))}")
        logger.info(f"Products with prices: {sum(1 for p in products if p.get('price'))}")
        logger.info(f"Products with SKU: {sum(1 for p in products if p.get('product_id_sku'))}")
        logger.info(f"Products with images: {sum(1 for p in products if p.get('product_image_url'))}")
        logger.info(f"Products with brand: {sum(1 for p in products if p.get('brand_name'))}")
        
        if not ingredient_analysis.empty:
            logger.info(f"Product pairs with 2+ shared ingredients: {len(ingredient_analysis)}")
        
        # Show sample data
        logger.info(f"\n=== SAMPLE PRODUCTS ===")
        for i, product in enumerate(products[:3], 1):
            logger.info(f"{i}. {product.get('product_name', 'Unknown')}")
            logger.info(f"   SKU: {product.get('product_id_sku', 'N/A')}")
            logger.info(f"   Brand: {product.get('brand_name', 'N/A')}")
            logger.info(f"   Price: {product.get('price', 'N/A')}")
            
            ingredients = product.get('ingredients', '')
            if ingredients:
                logger.info(f"   Ingredients: {ingredients[:100]}{'...' if len(ingredients) > 100 else ''}")
            else:
                logger.info(f"   Ingredients: N/A")
        
        logger.info("Scraping completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main() 