#!/usr/bin/env python3
"""
Comprehensive test suite for the Beto Cosmetics scraper.

Tests all major functionality including:
- Product discovery via Shopify JSON API
- Data extraction and validation
- Ingredient overlap analysis
- Error handling and edge cases
"""

import pytest
import requests
import json
import pandas as pd
from unittest.mock import Mock, patch
import tempfile
import os
import sys
import requests_mock

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from beto_cosmetics_scraper_v2 import BetoCosmeticsScraperV2, analyze_ingredient_overlap


class TestBetoCosmeticsScraper:
    """Test suite for the BetoCosmeticsScraper class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.scraper = BetoCosmeticsScraperV2(delay=0.1)  # Fast delay for testing
        
        # Sample product data for testing
        self.sample_shopify_product = {
            "id": 123456,
            "title": "Test Beauty Cream 50ml",
            "handle": "test-beauty-cream-50ml",
            "body_html": "<p>A wonderful beauty cream with natural ingredients.</p>",
            "vendor": "Test Brand",
            "product_type": "Skincare",
            "variants": [
                {
                    "id": 789012,
                    "sku": "TBC001",
                    "price": "25.00",
                    "compare_at_price": "30.00",
                    "barcode": "1234567890123"
                }
            ],
            "images": [
                {
                    "src": "//example.com/test-product.jpg"
                }
            ]
        }
        
        self.sample_api_response = {
            "products": [self.sample_shopify_product]
        }
    
    def test_initialization(self):
        """Test scraper initialization."""
        scraper = BetoCosmeticsScraperV2()
        
        assert scraper.base_url == "https://betocosmetics.com"
        assert scraper.delay == 1.0
        assert scraper.products_data == []
        assert scraper.failed_urls == []
        assert 'User-Agent' in scraper.session.headers
    
    def test_initialization_with_custom_params(self):
        """Test scraper initialization with custom parameters."""
        custom_url = "https://example.com"
        custom_delay = 2.0
        
        scraper = BetoCosmeticsScraperV2(base_url=custom_url, delay=custom_delay)
        
        assert scraper.base_url == custom_url
        assert scraper.delay == custom_delay
    
    def test_get_products_from_json_api_success(self, requests_mock):
        """Test successful product fetch from JSON API."""
        # Mock the API response
        requests_mock.get(
            "https://betocosmetics.com/products.json",
            json=self.sample_api_response
        )
        
        products = self.scraper.get_products_from_json_api(limit=1)
        
        assert len(products) == 1
        assert products[0]['title'] == "Test Beauty Cream 50ml"
        assert products[0]['vendor'] == "Test Brand"
    
    def test_get_products_from_json_api_empty_response(self, requests_mock):
        """Test API response with no products."""
        requests_mock.get(
            "https://betocosmetics.com/products.json",
            json={"products": []}
        )
        
        products = self.scraper.get_products_from_json_api(limit=5)
        
        assert len(products) == 0
    
    def test_get_products_from_json_api_network_error(self, requests_mock):
        """Test handling of network errors."""
        requests_mock.get(
            "https://betocosmetics.com/products.json",
            exc=requests.exceptions.ConnectionError("Network error")
        )
        
        products = self.scraper.get_products_from_json_api(limit=5)
        
        assert len(products) == 0
    
    def test_get_additional_product_data_success(self, requests_mock):
        """Test successful additional data extraction."""
        # Mock product page with ingredients
        product_html = """
        <html>
        <body>
        <div class="ingredients">
        Ingredients: Water, Glycerin, Vitamin E, Aloe Vera Extract
        </div>
        <div class="barcode">EAN: 1234567890123</div>
        </body>
        </html>
        """
        
        requests_mock.get("https://betocosmetics.com/products/test-product", text=product_html)
        
        additional_data = self.scraper.get_additional_product_data(
            "https://betocosmetics.com/products/test-product"
        )
        
        assert 'ingredients' in additional_data
        assert 'Water, Glycerin, Vitamin E, Aloe Vera Extract' in additional_data['ingredients']
        assert additional_data.get('barcode_ean_upc') == '1234567890123'
    
    def test_get_additional_product_data_network_error(self, requests_mock):
        """Test handling of network errors in additional data fetch."""
        requests_mock.get(
            "https://betocosmetics.com/products/test-product",
            exc=requests.exceptions.Timeout("Timeout error")
        )
        
        additional_data = self.scraper.get_additional_product_data(
            "https://betocosmetics.com/products/test-product"
        )
        
        assert additional_data == {}
        assert "https://betocosmetics.com/products/test-product" in self.scraper.failed_urls
    
    def test_process_shopify_product_basic(self):
        """Test basic product processing from Shopify JSON."""
        product_data = self.scraper.process_shopify_product(
            self.sample_shopify_product, 
            fetch_additional=False
        )
        
        assert product_data is not None
        assert product_data['product_name'] == "Test Beauty Cream 50ml"
        assert product_data['brand_name'] == "Test Brand"
        assert product_data['product_id_sku'] == "TBC001"
        assert product_data['price'] == "BD 25.00 (was BD 30.00)"
        assert product_data['product_image_url'] == "https://example.com/test-product.jpg"
        assert product_data['barcode_ean_upc'] == "1234567890123"
        assert product_data['website_name'] == "Beto Cosmetics"
        assert "test-beauty-cream-50ml" in product_data['product_url']
    
    def test_process_shopify_product_minimal_data(self):
        """Test product processing with minimal data."""
        minimal_product = {
            "title": "Minimal Product",
            "handle": "minimal-product",
            "vendor": "",
            "variants": [],
            "images": []
        }
        
        product_data = self.scraper.process_shopify_product(
            minimal_product, 
            fetch_additional=False
        )
        
        assert product_data is not None
        assert product_data['product_name'] == "Minimal Product"
        assert product_data['brand_name'] == ""
        assert product_data['product_id_sku'] == ""
        assert product_data['price'] == ""
        assert product_data['product_image_url'] == ""
        assert product_data['barcode_ean_upc'] == ""
    
    def test_process_shopify_product_with_error(self):
        """Test product processing with malformed data."""
        malformed_product = None
        
        product_data = self.scraper.process_shopify_product(
            malformed_product, 
            fetch_additional=False
        )
        
        assert product_data is None
    
    def test_scrape_products_success(self, requests_mock):
        """Test successful full scraping workflow."""
        # Mock API response
        requests_mock.get(
            "https://betocosmetics.com/products.json",
            json={"products": [self.sample_shopify_product] * 3}
        )
        
        # Mock product pages
        product_html = "<html><body><div>Product page</div></body></html>"
        requests_mock.get(requests_mock.ANY, text=product_html)
        
        products = self.scraper.scrape_products(min_products=2, fetch_additional=False)
        
        assert len(products) >= 2
        assert all('product_name' in product for product in products)
        assert all('website_name' in product for product in products)
    
    def test_scrape_products_api_failure(self, requests_mock):
        """Test scraping when API fails."""
        requests_mock.get(
            "https://betocosmetics.com/products.json",
            status_code=500
        )
        
        products = self.scraper.scrape_products(min_products=5)
        
        assert len(products) == 0
    
    def test_save_to_csv_success(self):
        """Test successful CSV export."""
        # Add sample data
        self.scraper.products_data = [
            {
                'product_id_sku': 'TEST001',
                'product_name': 'Test Product',
                'brand_name': 'Test Brand',
                'price': 'BD 10.00',
                'website_name': 'Beto Cosmetics',
                'product_line_name': 'Test Line',
                'product_image_url': 'https://example.com/image.jpg',
                'barcode_ean_upc': '123456789',
                'ingredients': 'Water, Glycerin'
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            try:
                self.scraper.save_to_csv(tmp_file.name)
                
                # Verify file was created and has correct content
                assert os.path.exists(tmp_file.name)
                
                df = pd.read_csv(tmp_file.name)
                assert len(df) == 1
                assert 'product_id_sku' in df.columns
                assert df.iloc[0]['product_name'] == 'Test Product'
                
            finally:
                # Clean up
                if os.path.exists(tmp_file.name):
                    os.unlink(tmp_file.name)
    
    def test_save_to_csv_no_data(self):
        """Test CSV export with no data."""
        # Ensure no data
        self.scraper.products_data = []
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            try:
                self.scraper.save_to_csv(tmp_file.name)
                
                # File should not be created when no data
                # (This depends on implementation - adjust if needed)
                
            finally:
                # Clean up
                if os.path.exists(tmp_file.name):
                    os.unlink(tmp_file.name)


class TestIngredientAnalysis:
    """Test suite for ingredient overlap analysis functionality."""
    
    def test_analyze_ingredient_overlap_basic(self):
        """Test basic ingredient overlap analysis."""
        products_data = [
            {
                'product_name': 'Product A',
                'ingredients': 'Water, Glycerin, Vitamin E, Aloe Vera'
            },
            {
                'product_name': 'Product B', 
                'ingredients': 'Glycerin, Vitamin E, Coconut Oil, Shea Butter'
            },
            {
                'product_name': 'Product C',
                'ingredients': 'Water, Coconut Oil, Jojoba Oil'
            }
        ]
        
        result_df = analyze_ingredient_overlap(products_data)
        
        assert not result_df.empty
        assert 'product_1' in result_df.columns
        assert 'product_2' in result_df.columns
        assert 'shared_ingredients_count' in result_df.columns
        assert 'shared_ingredients' in result_df.columns
        assert 'ingredient_group' in result_df.columns
        
        # Should find overlap between A & B (glycerin, vitamin e)
        ab_overlap = result_df[
            ((result_df['product_1'] == 'Product A') & (result_df['product_2'] == 'Product B')) |
            ((result_df['product_1'] == 'Product B') & (result_df['product_2'] == 'Product A'))
        ]
        assert len(ab_overlap) == 1
        assert ab_overlap.iloc[0]['shared_ingredients_count'] >= 2
    
    def test_analyze_ingredient_overlap_no_overlap(self):
        """Test ingredient analysis with no significant overlap."""
        products_data = [
            {
                'product_name': 'Product A',
                'ingredients': 'Water, Glycerin'
            },
            {
                'product_name': 'Product B',
                'ingredients': 'Coconut Oil, Shea Butter'
            }
        ]
        
        result_df = analyze_ingredient_overlap(products_data)
        
        # Should be empty as no products share 2+ ingredients
        assert result_df.empty
    
    def test_analyze_ingredient_overlap_empty_ingredients(self):
        """Test ingredient analysis with empty ingredient lists."""
        products_data = [
            {
                'product_name': 'Product A',
                'ingredients': ''
            },
            {
                'product_name': 'Product B',
                'ingredients': 'Water, Glycerin'
            }
        ]
        
        result_df = analyze_ingredient_overlap(products_data)
        
        # Should be empty as one product has no ingredients
        assert result_df.empty
    
    def test_analyze_ingredient_overlap_complex_ingredients(self):
        """Test ingredient analysis with complex ingredient lists."""
        products_data = [
            {
                'product_name': 'Complex Product A',
                'ingredients': 'Aqua (Water), Glycerin, Sodium Hyaluronate; Vitamin E Acetate, Fragrance'
            },
            {
                'product_name': 'Complex Product B',
                'ingredients': 'Water, Glycerin, Vitamin E Acetate, Coconut Oil (Cocos Nucifera)'
            }
        ]
        
        result_df = analyze_ingredient_overlap(products_data)
        
        # Should find overlap despite complex formatting
        assert not result_df.empty
        overlap_row = result_df.iloc[0]
        assert overlap_row['shared_ingredients_count'] >= 2
    
    def test_analyze_ingredient_overlap_case_insensitive(self):
        """Test that ingredient analysis is case insensitive."""
        products_data = [
            {
                'product_name': 'Product A',
                'ingredients': 'WATER, GLYCERIN, vitamin e'
            },
            {
                'product_name': 'Product B',
                'ingredients': 'water, Glycerin, VITAMIN E'
            }
        ]
        
        result_df = analyze_ingredient_overlap(products_data)
        
        assert not result_df.empty
        overlap_row = result_df.iloc[0]
        assert overlap_row['shared_ingredients_count'] == 3


class TestValidationAndEdgeCases:
    """Test suite for validation and edge cases."""
    
    def test_required_fields_present(self):
        """Test that all required fields are present in scraped data."""
        scraper = BetoCosmeticsScraperV2()
        
        sample_product = {
            "title": "Test Product",
            "handle": "test-product",
            "vendor": "Test Brand",
            "variants": [{"sku": "TEST001", "price": "10.00"}],
            "images": [{"src": "//example.com/image.jpg"}]
        }
        
        product_data = scraper.process_shopify_product(sample_product, fetch_additional=False)
        
        required_fields = [
            'product_id_sku', 'product_line_name', 'brand_name', 'product_name',
            'product_image_url', 'barcode_ean_upc', 'ingredients', 'price', 'website_name'
        ]
        
        for field in required_fields:
            assert field in product_data, f"Required field '{field}' missing"
    
    def test_data_types_validation(self):
        """Test that data types are correct."""
        scraper = BetoCosmeticsScraperV2()
        
        sample_product = {
            "title": "Test Product",
            "handle": "test-product", 
            "vendor": "Test Brand",
            "variants": [{"sku": "TEST001", "price": "10.00"}],
            "images": [{"src": "//example.com/image.jpg"}]
        }
        
        product_data = scraper.process_shopify_product(sample_product, fetch_additional=False)
        
        # All values should be strings
        for key, value in product_data.items():
            assert isinstance(value, str), f"Field '{key}' should be string, got {type(value)}"
    
    def test_url_handling(self):
        """Test proper URL handling and construction."""
        scraper = BetoCosmeticsScraperV2()
        
        # Test relative URL conversion
        sample_product = {
            "title": "Test Product",
            "handle": "test-product",
            "vendor": "Test Brand",
            "variants": [{"sku": "TEST001", "price": "10.00"}],
            "images": [{"src": "/relative/image.jpg"}]
        }
        
        product_data = scraper.process_shopify_product(sample_product, fetch_additional=False)
        
        assert product_data['product_url'].startswith('https://')
        assert product_data['product_image_url'].startswith('https://')
    
    @pytest.mark.parametrize("price,compare_price,expected", [
        ("10.00", None, "BD 10.00"),
        ("10.00", "15.00", "BD 10.00 (was BD 15.00)"),
        ("10.00", "10.00", "BD 10.00"),  # Same price, no "was" text
        ("", None, ""),
        (None, None, ""),
    ])
    def test_price_formatting(self, price, compare_price, expected):
        """Test various price formatting scenarios."""
        scraper = BetoCosmeticsScraperV2()
        
        variant_data = {"sku": "TEST001"}
        if price is not None:
            variant_data["price"] = price
        if compare_price is not None:
            variant_data["compare_at_price"] = compare_price
        
        sample_product = {
            "title": "Test Product",
            "handle": "test-product",
            "vendor": "Test Brand",
            "variants": [variant_data] if price else [],
            "images": []
        }
        
        product_data = scraper.process_shopify_product(sample_product, fetch_additional=False)
        
        assert product_data['price'] == expected


def test_integration_workflow():
    """Integration test for the complete workflow."""
    with requests_mock.Mocker() as m:
        # Mock successful API response
        api_response = {
            "products": [
                {
                    "title": "Integration Test Product 1",
                    "handle": "integration-test-1",
                    "vendor": "Test Brand",
                    "variants": [{"sku": "INT001", "price": "20.00"}],
                    "images": [{"src": "//example.com/int1.jpg"}]
                },
                {
                    "title": "Integration Test Product 2", 
                    "handle": "integration-test-2",
                    "vendor": "Test Brand",
                    "variants": [{"sku": "INT002", "price": "25.00"}],
                    "images": [{"src": "//example.com/int2.jpg"}]
                }
            ]
        }
        
        m.get("https://betocosmetics.com/products.json", json=api_response)
        
        # Mock product pages with ingredients
        product_html = """
        <html><body>
        <div class="ingredients">Ingredients: Water, Glycerin, Vitamin E</div>
        </body></html>
        """
        m.get(requests_mock.ANY, text=product_html)
        
        # Run full workflow
        scraper = BetoCosmeticsScraperV2(delay=0.1)
        products = scraper.scrape_products(min_products=2, fetch_additional=True)
        
        # Validate results
        assert len(products) == 2
        assert all('product_name' in p for p in products)
        assert all('brand_name' in p for p in products)
        
        # Test ingredient analysis
        analysis_df = analyze_ingredient_overlap(products)
        
        # Should find overlap since both products will have same mocked ingredients
        assert not analysis_df.empty


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"]) 