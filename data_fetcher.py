from datetime import datetime
import re

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_bull_shoals_data():
    """Scrape the Bull Shoals Dam data table from the website using Playwright."""
    url = "https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm"
    
    try:
        with sync_playwright() as p:
            # Launch browser with ignore-certificate-errors flag to bypass SSL issues
            browser = p.chromium.launch(
                args=["--ignore-certificate-errors"],
                headless=True
            )
            
            # Create a new page and navigate to the URL
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)

            # Get the page content
            html_content = page.content()

            # Close the browser
            browser.close()

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find the table data between the two horizontal rules
        content = str(soup)

        # Try to find the table between <hr> tags
        try:
            table_section = content.split("<hr>")[1].split("<hr>")[0]
        except IndexError:
            # If we can't find the HR tags, look for the table directly
            table_section = content

        # Parse the data into a structured format
        lines = table_section.strip().split('\n')
        data = []
        
        for line in lines:
            # Skip header lines and empty lines
            if not re.search(r'\d{2}[A-Z]{3}\d{4}', line):
                continue
                
            # Extract data using regex - more flexible to handle different month formats
            match = re.search(r'(\d{2}[A-Z]{3}\d{4})\s+(\d{4})\s+(\d+\.\d+|\-+)\s+(\d+\.\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)', line)
            if match:
                date_str, time_str, elevation, tailwater, generation, turbine_release, spillway_release, total_release = match.groups()
                
                # Convert to appropriate data types
                try:
                    date_time = datetime.strptime(f"{date_str} {time_str}", "%d%b%Y %H%M")
                    elevation = float(elevation) if elevation != '----' else None
                    tailwater = float(tailwater) if tailwater != '----' else None
                    generation = int(generation) if generation != '----' else None
                    turbine_release = int(turbine_release) if turbine_release != '----' else None
                    spillway_release = int(spillway_release) if spillway_release != '----' else None
                    total_release = int(total_release) if total_release != '----' else None
                    
                    entry_data = {
                        'date_time': date_time,
                        'elevation': elevation,
                        'tailwater': tailwater,
                        'generation': generation,
                        'turbine_release': turbine_release,
                        'spillway_release': spillway_release,
                        'total_release': total_release
                    }
                    data.append(entry_data)
                except ValueError:
                    # Skip entries with invalid data
                    continue
        
        if data:
            return data
        else:
            return get_sample_data()
            
    except Exception as e:
        print(f"Error fetching data: {e}")
        return get_sample_data()

def get_sample_data():
    """Return error data when web scraping fails."""
    # Return a minimal dataset with just the current time and an error indicator
    current_time = datetime.now()
    error_data = [{
        'date_time': current_time,
        'elevation': None,
        'tailwater': None,
        'generation': None,
        'turbine_release': 0,  # Using 0 as an error indicator
        'spillway_release': 0,
        'total_release': 0,
        'error': True  # Flag to indicate this is error data
    }]
    
    return error_data
