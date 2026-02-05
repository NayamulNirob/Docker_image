import re
import datetime
import requests
import unicodedata
from bs4 import BeautifulSoup
import json
import time
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
start_time = datetime.datetime.now()
logging.info(f"Scraping started at: {start_time}")



class SlovakPartnerScraper:

    BASE_URL = "https://rpvs.gov.sk/rpvs/Partner/Partner/Detail/"

    def __init__(self, start, end, output_file, cache_file, delay=0.2):

        self.start = start
        self.end = end
        self.output_file = output_file
        self.delay = delay
        self.all_data = []
        self.cache_file = cache_file

        # Load cache if exists
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                self.processed_ids = set(json.load(f))
        else:
            self.processed_ids = set()

        # Load existing data if exists
        if os.path.exists(self.output_file):
            with open(self.output_file, "r", encoding="utf-8") as f:
                self.all_data = json.load(f)
        else:
            self.all_data = []

        # os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        # os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        output_dir = os.path.dirname(self.output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)


    # --------------------------
    # Utility methods
    # --------------------------
    @staticmethod
    def convert_to_english(text):
        if not text:
            return None
        text = unicodedata.normalize("NFKD", text)
        return text.encode("ascii", "ignore").decode("ascii")

    @staticmethod
    def get_field(soup, label_text):
        for group in soup.find_all("div", class_="form-group"):
            label = group.find("label")
            if label and label_text in label.get_text(strip=True):
                p = group.find("p", class_="form-control-static")
                if p:
                    return p.get_text(strip=True)
        return None

    @staticmethod
    def get_pdf_url(soup, label_text, base_url="https://rpvs.gov.sk"):
        for group in soup.find_all("div", class_="form-group"):
            label = group.find("label")
            if label and label_text in label.get_text(strip=True):
                a_tag = group.find("a", href=True)
                if a_tag:
                    return base_url + a_tag["href"]
        return None

    def parse_bo_table(self, soup):
        bo_table = soup.find("table", class_="table")
        bos = []

        if bo_table:
            for row in bo_table.find("tbody").find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 4:
                    first_col = cols[0].get_text(" ", strip=True)

                    if first_col.startswith("Meno a priezvisko"):
                        first_col = first_col.replace(
                            "Meno a priezvisko", ""
                        ).strip()

                    name_part = first_col.split("Dátum narodenia")[0].strip()

                    bos.append({
                        "Name and surname of the BO": self.convert_to_english(name_part),
                        "Date of Birth": self.convert_to_english(
                            cols[1].get_text(strip=True)
                        ),
                        "Nationality": self.convert_to_english(
                            cols[2].get_text(strip=True)
                        ),
                        "Address of the BO": self.convert_to_english(
                            cols[3].get_text(strip=True)
                        )
                    })
        return bos

    @staticmethod
    def parse_address(full_address):
        if not full_address:
            return {}

        address = full_address.strip()

        # List of known countries (add more if needed)
        countries = [
            "Slovenska republika", "Turecka republika", "Hongkong",
            "Holandske kralovstvo", "Polska republika", "Kajmanie ostrovy",
            "Rakuska republika", "Talianska republika", "Nemecka spolkova republika",
            "Spojene staty americke", "Spojene arabske emiraty", "Ruska federacia",
            "Kanada", "Bosna a Hercegovina", "Indicka republika","Ceska republika"
        ]

        # Split the address into parts
        parts = [p.strip() for p in address.split(",")]

        if len(parts) >= 2:
            street_part = parts[0]
            zip_city_country = ", ".join(parts[1:])

            # Extract ZIP and city
            zip_match = re.match(r"(\d{3}\s?\d{2})\s*(.*)", zip_city_country)
            if zip_match:
                postal_code = zip_match.group(1).strip()
                city_country = zip_match.group(2).strip()

                # Detect country
                country_found = None
                for c in countries:
                    if c.lower() in city_country.lower():
                        country_found = c
                        city_country = city_country.replace(c, "").strip(", ").strip()
                        break

                return {
                    "Address": street_part,
                    "PostalCode": postal_code,
                    "City": city_country if city_country else None,
                    "Country": country_found if country_found else None
                }

        # Fallback if parsing fails
        return {"Address": address, "PostalCode": None, "City": None, "Country": None}

    # --------------------------
    # Core scraping logic
    # --------------------------
    def scrape_partner(self, partner_id):
        url = f"{self.BASE_URL}{partner_id}"
        logging.info(f"Processing partner ID: {partner_id}")

        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )

        if response.status_code != 200:
            logging.warning(f"Failed to fetch ID {partner_id}")
            return None

        html = self.convert_to_english(response.text)
        soup = BeautifulSoup(html, "html.parser")

        bos = self.parse_bo_table(soup)
        if not bos:
            logging.warning(f"Skipping ID {partner_id} (no Beneficial Owners)")
            return None

        # Parse Business Address
        full_address = self.get_field(soup, "Adresa sídla")
        parsed_business_address = self.parse_address(self.convert_to_english(full_address))

        # Parse BO addresses
        for bo in bos:
            bo_full_address = bo.get("Address of the BO")
            bo["Address of the BO"] = self.parse_address(bo_full_address)

        return {
            "Business Name": self.convert_to_english(
                self.get_field(soup, "Obchodné meno")
            ),
            "ICO": self.convert_to_english(
                self.get_field(soup, "IČO")
            ),
            "Address": parsed_business_address,
            "Verification Date": self.convert_to_english(
                self.get_field(soup, "Dátum overenia")
            ),
            "Verification document URL": self.convert_to_english(
                self.get_pdf_url(soup, "Verifikačný dokument (pdf)")
            ),
            "Beneficial Owners": bos,
            "Source URL": url
        }

    def run(self):
        for partner_id in range(self.start, self.end+1):
            url = f"{self.BASE_URL}{partner_id}"
            if url in self.processed_ids:
                logging.info(f"[SKIPPED] Already processed: {url}")
                continue
            try:
                data = self.scrape_partner(partner_id)
                if data:
                    self.all_data.append(data)
                    logging.info(f"[SAVED] Partner ID {partner_id}: {data['Business Name']}")
                    # Add URL to cache
                    self.processed_ids.add(url)
                    with open(self.cache_file, "w") as f:
                        sorted_urls = sorted(list(self.processed_ids), key=lambda x: int(x.split("/")[-1]))
                        json.dump(sorted_urls, f,indent=2)

                    # Save JSON incrementally (optional)
                    with open(self.output_file, "w", encoding="utf-8") as f:
                        json.dump(self.all_data, f, ensure_ascii=False, indent=2)

                    time.sleep(self.delay)
            except Exception as e:
                logging.warning(f"Error at ID {partner_id}: {e}")

    def save_to_json(self):
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.all_data, f, ensure_ascii=False, indent=2)

        logging.info(f"Data saved to: {os.path.abspath(self.output_file)}")

    @staticmethod
    def get_total_records(): # To collect total records of data number
        url = "https://rpvs.gov.sk/rpvs/Partner/Partner/VyhladavaniePartneraData"

        response = requests.post(url, timeout=15)
        response.raise_for_status()

        data = response.json()
        return data["recordsTotal"]


# --------------------------
# Run scraper
# --------------------------
if __name__ == "__main__":

    total_records = SlovakPartnerScraper.get_total_records()
    logging.info(f"Total records detected: {total_records}")

    scraper = SlovakPartnerScraper(
        start=1,
        end=total_records,  # change to dynamic "total_records" which is now 50887
        output_file="outputfile/slavak_public_partners_register_data.json", # for store Json data
        cache_file="cache/slavak_public_partners_register_cache_ids.json", # for store cachURLS

    )

    scraper.run()
    scraper.save_to_json()
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    logging.info(f"Scraping finished at: {end_time}")
    logging.info(f"Scraping completed! Total execution time: {duration}")