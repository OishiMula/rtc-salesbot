# Twitter sales bot created by Oishi Mula for usage at Raging Teens Clan NFT.
# Copyright (c) 2022, Oishi Mula
# All rights reserved.
# This source code is licensed under the MIT-style license found in the
# LICENSE file in the root directory of this source tree. 
import logging
import os
import pickle
import time
from pathlib import Path

import requests
import tweepy
from dotenv import load_dotenv
from pycoingecko import CoinGeckoAPI
from ratelimit import limits
from requests.adapters import HTTPAdapter, Retry

load_dotenv()

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M'
)

# Creating the Twitter tweepy connection for V1.1 (media_upload)
twitter_auth = tweepy.OAuth1UserHandler(
    consumer_key=os.getenv('consumer_key'),
    consumer_secret=os.getenv('consumer_secret'),
    access_token=os.getenv('access_token'),
    access_token_secret=os.getenv('access_token_secret')
)

twitter = tweepy.API(
    twitter_auth,
    retry_count = 5,
    retry_delay = 10,
    wait_on_rate_limit=True
)

cg = CoinGeckoAPI()

# Project name and file to store last tweeted information
PROJECT = "Raging Teens Clan"
LAST_TWEETED_RTC_FILE = Path('last_sold.dat')
LAST_TWEETED_FURIN_FILE = Path('last_furin_sold.dat')
MINUTE = 60
ADA = '₳'

# The function to retrieve the JSON listings
def retrieve_sales(p, page_num):
    opencnft_session = requests.Session()
    retries = Retry(
        total = 5,
        connect = 3,
        read = 3,
        backoff_factor = 0.3,
    )
    adapter = HTTPAdapter(max_retries=retries)
    opencnft_session.mount("https://", adapter)

    # These endpoints can be changed, either with a .env or hard-code a URL.
    project1_api = f"https://api.opencnft.io/1/policy/{os.getenv('project1')}/transactions?page={page_num}&order=date"
    project2_api = f"https://api.opencnft.io/1/policy/{os.getenv('project2')}/transactions?page={page_num}&order=date"
    
    while True:
        try:
            match p:
                case 'rtc':
                    opencnft_response = opencnft_session.get(f'{project1_api}')
                case 'furin':
                    opencnft_response = opencnft_session.get(f'{project2_api}')
            opencnft_response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            logging.warning(f"{e} - Retrying")
            time.sleep(5)
            continue

        except requests.exceptions.RequestException as e:
            logging.error("Endpoint failure - going to sleep.")
            time.sleep(300)
            continue

        break
    return opencnft_response.json()

# Cycle through the pages on OpenCNFT
def next_page(p, page_num):
    page_num += 1
    return retrieve_sales(p, page_num), page_num

def prev_page(p, page_num):
    page_num -= 1
    num = 19
    return retrieve_sales(p, page_num), page_num, num

def compare_listing(project, file):
    # setting enviroment up
    check_flag = True
    num = 0
    page_num = 1
    total_listings = 0

    last_tweeted = pickle.load(open(file, 'rb'))
    cnft_listing = retrieve_sales(project, page_num)
    if cnft_listing == None:
        time.sleep(120)
        return
        
    while check_flag == True:
        # Check the listing downloaded and compare to what was last tweeted
        # If downloaded listing is newer, check the next listing / page
        if int(cnft_listing['items'][num]['sold_at']) > int(last_tweeted['sold_at']):
            logging.info(f"Listing #{total_listings} - {cnft_listing['items'][num]['unit_name']} is a new sale.")
            total_listings += 1
            num += 1
            if num == 20:
                logging.info("Retrieving next page listings.")
                num = 0
                (cnft_listing, page_num) = next_page('rtc', page_num)
            time.sleep(1)

        # If there were new listings, begin to tweet them from oldest to newest.
        elif num > 0:
            logging.info(f"Found {total_listings} listing{'' if total_listings == 1 else 's'}.")
            while num > 0 or page_num > 1:
                num -= 1
                tweet_sale(cnft_listing['items'][num])
                if num == 0 and page_num > 1:
                    (cnft_listing, page_num, num) = prev_page('rtc', page_num)
                time.sleep(3)
            pickle.dump(cnft_listing['items'][num], open(file, 'wb'))
            check_flag = False
            
        # If there was nothing new - skip to end.
        else:
            check_flag = False 

# Creating a payload message to tweet
def tweet_sale(listing):
    asset = listing['unit_name']
    sold_price = int(float(listing['price']) / 1000000)
    asset_mp = listing['marketplace']
    asset_img_raw = listing['thumbnail']['thumbnail'][7:]

    # Making exception incase CoinGecko / Twitter are having issues
    while True:
        try:
            asset_media_id = retrieve_media_id(asset_img_raw)
            usd = cg.get_price(ids='cardano', vs_currencies='usd')
            twitter.update_status(status=f"{asset} was purchased from {asset_mp} for the price of {ADA}{sold_price:,} (${(usd['cardano']['usd'] * sold_price):,.2f}).", media_ids=[asset_media_id.media_id])
            logging.info(f"{asset} - Purchased for {ADA}{sold_price:,}")
            break
        except (requests.exceptions.RequestException, tweepy.TweepyException) as e:
            logging.error(f"{asset} - Error! Retrying...")
            time.sleep(120)
            continue        

def retrieve_media_id(img_raw):
    ipfs_base = 'https://infura-ipfs.io/ipfs/'
    asset_img = requests.get(f"{ipfs_base}{img_raw}")
    if asset_img.status_code == 200:
        with open("image.png", 'wb') as f:
            f.write(asset_img.content)
            media_id = twitter.media_upload("image.png")
        os.remove('image.png')
        return media_id
    else:
        return twitter.media_upload("404.jpg")


@limits(calls=30, period=MINUTE)
def main():
    # Upon starting, it will check for a last_sold files. If none exist, it will enter the most recent sale to begin the monitor.
    logging.info(f"Starting the {PROJECT} Twitter bot.")
    if LAST_TWEETED_RTC_FILE.is_file() == False:
        logging.warning(f"{LAST_TWEETED_RTC_FILE} not found. Creating file now.")
        cnft_listing = retrieve_sales('rtc', 1)
        pickle.dump(cnft_listing['items'][0], open(LAST_TWEETED_RTC_FILE, 'wb'))
    if LAST_TWEETED_FURIN_FILE.is_file() == False:
        logging.warning(f"{LAST_TWEETED_FURIN_FILE} not found. Creating file now.")
        cnft_listing = retrieve_sales('furin', 1)
        pickle.dump(cnft_listing['items'][0], open(LAST_TWEETED_FURIN_FILE, 'wb'))

    while True:
        raging_teens = 'rtc'
        furins = 'furin'

        # The main function to post on twitter if changes are detected
        compare_listing(raging_teens, LAST_TWEETED_RTC_FILE)
        compare_listing(furins, LAST_TWEETED_FURIN_FILE)
        time.sleep(30)

if __name__ == "__main__":
    main()
