"""
Product Library
===============
Central product library for the curated motorcycle recommendation platform.

This module is the single source of truth for loading, filtering, validating,
and managing the product catalog. It separates editorial data (owned by us)
from Amazon data (changes daily) and enforces product status throughout the
lifecycle.

Product Lifecycle:
    Discover -> Review -> Approve -> Add to Library -> Daily Sync -> Recommend

Data Structure:
    Each product has:
    - Identity: asin, slug, title, brand, category, type
    - Status: draft | approved | hidden | out_of_stock | discontinued
    - Editorial: score, pros, cons, features, fitment_notes, recommended_for, notes
    - Amazon: price, mrp, discount, rating, review_count, availability, etc.
    - Compatibility: compatible_bikes
    - Presentation: best_for, verdict

The library loads the nested JSON and flattens it into plain dicts that are
100% compatible with existing templates, product_engine.py, and generate.py.
Templates continue to access product.price, product.rating, etc. directly.
"""

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ===== Valid Product Statuses =====

VALID_STATUSES = {'draft', 'approved', 'review', 'hidden', 'out_of_stock', 'discontinued'}

# Statuses that should appear on the website.
WEBSITE_STATUSES = {'approved', 'out_of_stock', 'review'}

# Statuses that the recommendation engine should process.
RECOMMENDABLE_STATUSES = {'approved', 'review'}


# ===== Category Normalization Pipeline =====
# Every product gets exactly one canonical category (snake_case) during import.
# All code lookups use canonical categories. Display uses category_display.

CANONICAL_CATEGORIES = {
    # Safety Gear
    'helmet', 'helmet_accessories',
    # Riding Gear (specific)
    'gloves', 'jackets', 'riding_pants', 'knee_guard', 'ear_plugs',
    # Mounts & Navigation
    'phone_mount',
    # Protection
    'crash_guard', 'bike_cover', 'leg_guard', 'sump_guard',
    'radiator_guard', 'fork_sliders', 'frame_sliders', 'pillion_grab_rail',
    'luggage_rack', 'side_stand_extender', 'handlebar_risers', 'bar_end_weights',
    # Maintenance
    'chain_lube', 'chain_cleaner', 'engine_oil',
    # Inflation
    'tyre_inflator',
    # Luggage
    'tank_bag', 'saddle_bag', 'tail_bag',
    # Stickers & pads
    'tank_sticker', 'wheel_rim_tape',
    # Security & Power
    'usb_charger', 'disc_lock', 'chain_lock',
    # Other specific
    'action_camera', 'dash_cam', 'seat_cover', 'handlebar_grip',
    'mirror', 'windshield', 'gps_tracker', 'headlight', 'indicator',
    'horn', 'charger', 'footrest', 'alarm', 'tool_kit', 'polish',
    # Non-motorcycle (excluded from motorcycle guides/recommendations)
    'bicycle_helmet',
}

# ===== Two-Level Taxonomy =====
# Every product maps to (category, subcategory).
# Category is the high-level group. Subcategory is the specific type within it.
# The recommendation engine filters by BOTH.

TAXONOMY: Dict[str, Dict[str, List[str]]] = {
    'helmet': {
        'full_face': ['full face', 'full-face'],
        'modular': ['modular', 'flip up', 'flip-up'],
        'open_face': ['open face', 'open-face', 'half face', 'half helmet'],
    },
    'helmet_accessories': {
        'bluetooth_intercom': ['bluetooth', 'intercom', 'headset', 'communication system', 'wireless', 'earphone', 'microphone'],
        'visor': ['visor', 'face shield', 'anti-fog'],
        'camera': ['chin mount', 'helmet camera', 'helmet cam'],
        'cleaning_kit': ['helmet cleaner', 'visor cleaner', 'helmet wash'],
    },
    'riding_gear': {
        'gloves': ['gloves', 'glove'],
        'jacket': ['jacket', 'riding jacket', 'bomber jacket'],
        'pants': ['riding pants', 'riding trousers', 'motorcycle pants'],
        'boots': ['riding boots', 'motorcycle boots', 'bike boots'],
        'knee_guard': ['knee guard', 'knee pad', 'knee protector', 'knee armour'],
        'ear_plugs': ['ear plug', 'earplug', 'ear plugs'],
    },
    'maintenance': {
        'chain_lube': ['chain lube', 'chain spray', 'chain lubricant', 'chain wax'],
        'chain_cleaner': ['chain cleaner', 'chain clean'],
        'engine_oil': ['engine oil', 'motor oil', '10w-40', '10w-50', '20w-50'],
    },
    'security': {
        'disc_lock': ['disc lock', 'disk lock', 'brake lock'],
        'chain_lock': ['chain lock', 'security chain', 'anti-theft chain'],
    },
    'electronics': {
        'phone_mount': ['phone mount', 'phone holder', 'mobile holder', 'mobile mount', 'handlebar mount'],
        'usb_charger': ['usb charger', 'dual usb', 'quick charge', 'motorcycle charger'],
        'tpms': ['tyre inflator', 'tire inflator', 'air compressor', 'tyre pump', 'air pump', 'portable compressor'],
        'gps_tracker': ['gps tracker', 'vehicle tracker'],
    },
    'protection': {
        'crash_guard': ['crash guard', 'engine guard', 'frame slider', 'crash bar'],
        'leg_guard': ['leg guard', 'engine guard', 'crash guard'],
        'bike_cover': ['bike cover', 'motorcycle cover', 'body cover', 'dust cover', 'scooter cover'],
    },
    'bike_parts': {
        'sump_guard': ['sump guard', 'engine sump guard', 'lower engine guard', 'engine guard'],
        'radiator_guard': ['radiator guard', 'radiator cover', 'radiator grille'],
        'fork_sliders': ['fork slider', 'fork sliders', 'fork protector', 'fork cap'],
        'frame_sliders': ['frame slider', 'frame sliders', 'crash slider', 'crash sliders'],
        'pillion_grab_rail': ['pillion grab rail', 'grab rail', 'grab handle', 'pillion rail'],
        'luggage_rack': ['luggage rack', 'rear rack', 'top rack', 'carrier rack'],
        'side_stand_extender': ['side stand extender', 'side stand', 'kick stand plate', 'stand extender'],
        'handlebar_risers': ['handlebar riser', 'handlebar risers', 'riser', 'handle bar riser'],
        'bar_end_weights': ['bar end weight', 'bar end weights', 'handlebar weight', 'bar-end weight'],
        'tank_sticker': ['tank sticker', 'tank pad', 'tank stickers', 'tank decal', 'fuel tank pad'],
        'wheel_rim_tape': ['wheel rim tape', 'rim tape', 'rim sticker', 'wheel tape', 'rim strip'],
    },
    'luggage': {
        'tank_bag': ['tank bag', 'tankbag'],
        'saddle_bag': ['saddle bag', 'saddlebag', 'side bag', 'pannier'],
        'tail_bag': ['tail bag', 'rear bag', 'seat bag', 'backrest bag'],
    },
    'accessories_misc': {
        'seat_cover': ['seat cover'],
        'handlebar_grip': ['handlebar grip', 'handlebar grips'],
        'mirror': ['mirror', 'mirrors'],
        'windshield': ['windshield', 'windscreen'],
        'headlight': ['headlight', 'headlamp'],
        'indicator': ['indicator', 'turn signal'],
        'horn': ['horn'],
        'footrest': ['footrest', 'foot peg'],
        'alarm': ['alarm', 'anti-theft alarm'],
        'tool_kit': ['tool kit', 'toolkit'],
        'polish': ['polish', 'bike polish', 'wax'],
        'charger': ['charger'],
    },
    'cameras': {
        'action_camera': ['action camera', 'gopro', 'gopro mount', 'chest mount', 'helmet mount', 'selfie stick'],
        'dash_cam': ['dash cam', 'dashcam', 'car camera', 'car dvr'],
    },
}

# Category alias map that now includes helmet_accessories and helmet reclassification.
# The old flat CATEGORY_ALIASES still works for backward compatibility.
# New products should use the taxonomy directly.

# Maps old flat category values to new two-level taxonomy keys.
_CATEGORY_TO_TAXONOMY: Dict[str, str] = {
    'helmet': 'helmet',
    'gloves': 'riding_gear',
    'jackets': 'riding_gear',
    'riding_pants': 'riding_gear',
    'knee_guard': 'riding_gear',
    'ear_plugs': 'riding_gear',
    'phone_mount': 'electronics',
    'crash_guard': 'protection',
    'leg_guard': 'protection',
    'bike_cover': 'protection',
    'sump_guard': 'bike_parts',
    'radiator_guard': 'bike_parts',
    'fork_sliders': 'bike_parts',
    'frame_sliders': 'bike_parts',
    'pillion_grab_rail': 'bike_parts',
    'luggage_rack': 'bike_parts',
    'side_stand_extender': 'bike_parts',
    'handlebar_risers': 'bike_parts',
    'bar_end_weights': 'bike_parts',
    'tank_sticker': 'bike_parts',
    'wheel_rim_tape': 'bike_parts',
    'bicycle_helmet': 'bicycle_helmet',
    'chain_lube': 'maintenance',
    'chain_cleaner': 'maintenance',
    'engine_oil': 'maintenance',
    'tyre_inflator': 'electronics',
    'tank_bag': 'luggage',
    'saddle_bag': 'luggage',
    'tail_bag': 'luggage',
    'usb_charger': 'electronics',
    'disc_lock': 'security',
    'chain_lock': 'security',
    'action_camera': 'cameras',
    'dash_cam': 'cameras',
    'seat_cover': 'accessories_misc',
    'handlebar_grip': 'accessories_misc',
    'mirror': 'accessories_misc',
    'windshield': 'accessories_misc',
    'gps_tracker': 'electronics',
    'headlight': 'accessories_misc',
    'indicator': 'accessories_misc',
    'horn': 'accessories_misc',
    'charger': 'accessories_misc',
    'footrest': 'accessories_misc',
    'alarm': 'accessories_misc',
    'tool_kit': 'accessories_misc',
    'polish': 'accessories_misc',
}

# Master alias map: every known variant -> canonical snake_case category.
# Keys must be lowercase. Normalization handles case/whitespace.
CATEGORY_ALIASES: Dict[str, str] = {
    # Helmet
    'helmet': 'helmet',
    'helmets': 'helmet',
    'full face helmet': 'helmet',
    'modular helmet': 'helmet',
    'open face helmet': 'helmet',
    'half helmet': 'helmet',
    'dual visor helmet': 'helmet',
    'motorcycle helmet': 'helmet',
    'riding helmet': 'helmet',
    'bike helmet': 'helmet',
    'helmet bluetooth': 'helmet',
    'flip up helmet': 'helmet',
    'headgear': 'helmet',
    # Gloves
    'gloves': 'gloves',
    'riding gloves': 'gloves',
    'bike gloves': 'gloves',
    'racing gloves': 'gloves',
    'motorcycle gloves': 'gloves',
    'riding glove': 'gloves',
    # Jackets
    'jackets': 'jackets',
    'riding jacket': 'jackets',
    'bike jacket': 'jackets',
    'motorcycle jacket': 'jackets',
    'riding jackets': 'jackets',
    # Riding Pants
    'riding pants': 'riding_pants',
    'riding trousers': 'riding_pants',
    'motorcycle pants': 'riding_pants',
    # Knee Guard
    'knee guard': 'knee_guard',
    'knee guards': 'knee_guard',
    'knee pad': 'knee_guard',
    'knee pads': 'knee_guard',
    'knee protector': 'knee_guard',
    # Ear Plugs
    'ear plugs': 'ear_plugs',
    'ear plug': 'ear_plugs',
    'earplugs': 'ear_plugs',
    # Phone Mount
    'phone mount': 'phone_mount',
    'phone holder': 'phone_mount',
    'mobile holder': 'phone_mount',
    'mobile mount': 'phone_mount',
    'handlebar mount': 'phone_mount',
    'motorcycle phone mount': 'phone_mount',
    'bike phone mount': 'phone_mount',
    'mobile holder for bike': 'phone_mount',
    'motorcycle mobile holder': 'phone_mount',
    'motorcycle': 'phone_mount',
    # Crash Guard
    'crash guard': 'crash_guard',
    'engine guard': 'crash_guard',
    'leg guard': 'crash_guard',
    'crash protection': 'crash_guard',
    'frame slider': 'crash_guard',
    'crash bar': 'crash_guard',
    'engine protector': 'crash_guard',
    # Leg Guard (separate from crash guard per taxonomy)
    'leg guard': 'leg_guard',
    'leg guards': 'leg_guard',
    # Sump Guard
    'sump guard': 'sump_guard',
    'sump guards': 'sump_guard',
    'engine sump guard': 'sump_guard',
    # Radiator Guard
    'radiator guard': 'radiator_guard',
    'radiator guards': 'radiator_guard',
    'radiator cover': 'radiator_guard',
    # Fork Sliders
    'fork slider': 'fork_sliders',
    'fork sliders': 'fork_sliders',
    'fork protector': 'fork_sliders',
    # Frame Sliders
    'frame slider': 'frame_sliders',
    'frame sliders': 'frame_sliders',
    'crash slider': 'frame_sliders',
    # Pillion Grab Rail
    'pillion grab rail': 'pillion_grab_rail',
    'grab rail': 'pillion_grab_rail',
    'grab handle': 'pillion_grab_rail',
    # Luggage Rack
    'luggage rack': 'luggage_rack',
    'rear rack': 'luggage_rack',
    # Side Stand Extender
    'side stand extender': 'side_stand_extender',
    'side stand': 'side_stand_extender',
    'kick stand plate': 'side_stand_extender',
    # Handlebar Risers
    'handlebar riser': 'handlebar_risers',
    'handlebar risers': 'handlebar_risers',
    # Bar End Weights
    'bar end weight': 'bar_end_weights',
    'bar end weights': 'bar_end_weights',
    'handlebar weight': 'bar_end_weights',
    # Tank Sticker / Tank Pad
    'tank sticker': 'tank_sticker',
    'tank stickers': 'tank_sticker',
    'tank pad': 'tank_sticker',
    'tank decal': 'tank_sticker',
    'fuel tank pad': 'tank_sticker',
    # Wheel Rim Tape
    'wheel rim tape': 'wheel_rim_tape',
    'rim tape': 'wheel_rim_tape',
    'rim sticker': 'wheel_rim_tape',
    'wheel tape': 'wheel_rim_tape',
    # Bicycle / cycle helmet (excluded from motorcycle recommendations)
    'bicycle helmet': 'bicycle_helmet',
    'bike helmet cycle': 'bicycle_helmet',
    'cycle helmet': 'bicycle_helmet',
    'cycling helmet': 'bicycle_helmet',
    'kids helmet': 'bicycle_helmet',
    'kids cycle helmet': 'bicycle_helmet',
    # Bike Cover
    'bike cover': 'bike_cover',
    'motorcycle cover': 'bike_cover',
    'body cover': 'bike_cover',
    'bike body cover': 'bike_cover',
    'motorcycle body cover': 'bike_cover',
    'waterproof cover': 'bike_cover',
    'dust cover': 'bike_cover',
    'bike dust cover': 'bike_cover',
    'scooter cover': 'bike_cover',
    # Chain Lube
    'chain lube': 'chain_lube',
    'chain lubes': 'chain_lube',
    'chain spray': 'chain_lube',
    'chain lubricant': 'chain_lube',
    'chain wax': 'chain_lube',
    'chain lube spray': 'chain_lube',
    'bike chain lube': 'chain_lube',
    'motorcycle chain lube': 'chain_lube',
    # Chain Cleaner
    'chain cleaner': 'chain_cleaner',
    'chain cleaners': 'chain_cleaner',
    'chain cleaner spray': 'chain_cleaner',
    'chain clean': 'chain_cleaner',
    'bike chain cleaner': 'chain_cleaner',
    'motorcycle chain cleaner': 'chain_cleaner',
    # Engine Oil
    'engine oil': 'engine_oil',
    'engine oil 10w-40': 'engine_oil',
    'engine oil 10w-50': 'engine_oil',
    'engine oil 20w-50': 'engine_oil',
    'motor oil': 'engine_oil',
    'engine lubricant': 'engine_oil',
    # Tyre Inflator
    'tyre inflator': 'tyre_inflator',
    'tire inflator': 'tyre_inflator',
    'air compressor': 'tyre_inflator',
    'tyre pump': 'tyre_inflator',
    'air pump': 'tyre_inflator',
    'portable compressor': 'tyre_inflator',
    'tyre inflator pump': 'tyre_inflator',
    'air compressor for car': 'tyre_inflator',
    # Tank Bag
    'tank bag': 'tank_bag',
    'tankbag': 'tank_bag',
    'tank bag motorcycle': 'tank_bag',
    'motorcycle tank bag': 'tank_bag',
    # Saddle Bag
    'saddle bag': 'saddle_bag',
    'saddle bags': 'saddle_bag',
    'saddlebag': 'saddle_bag',
    'saddlebags': 'saddle_bag',
    'side bag': 'saddle_bag',
    'pannier': 'saddle_bag',
    'panniers': 'saddle_bag',
    'motorcycle saddle bag': 'saddle_bag',
    'bike saddle bag': 'saddle_bag',
    # Tail Bag
    'tail bag': 'tail_bag',
    'rear bag': 'tail_bag',
    'seat bag': 'tail_bag',
    'backrest bag': 'tail_bag',
    # USB Charger
    'usb charger': 'usb_charger',
    'dual usb': 'usb_charger',
    'bike charger': 'usb_charger',
    'motorcycle charger': 'usb_charger',
    'usb charging': 'usb_charger',
    'quick charge': 'usb_charger',
    # Disc Lock
    'disc lock': 'disc_lock',
    'disk lock': 'disc_lock',
    'brake lock': 'disc_lock',
    'disc brake lock': 'disc_lock',
    'bike disc lock': 'disc_lock',
    # Chain Lock
    'chain lock': 'chain_lock',
    'bike chain lock': 'chain_lock',
    'security chain': 'chain_lock',
    # Action Camera
    'action camera': 'action_camera',
    'action cameras': 'action_camera',
    # Dash Cam
    'dash cam': 'dash_cam',
    'dashcam': 'dash_cam',
    # Seat Cover
    'seat cover': 'seat_cover',
    'bike seat cover': 'seat_cover',
    'motorcycle seat cover': 'seat_cover',
    # Handlebar Grip
    'handlebar grip': 'handlebar_grip',
    'handlebar grips': 'handlebar_grip',
    # Mirror
    'mirror': 'mirror',
    'mirrors': 'mirror',
    'bike mirror': 'mirror',
    'motorcycle mirror': 'mirror',
    # Windshield
    'windshield': 'windshield',
    'windscreen': 'windshield',
    'motorcycle windshield': 'windshield',
    'bike windshield': 'windshield',
    # GPS Tracker
    'gps tracker': 'gps_tracker',
    'gps tracker for bike': 'gps_tracker',
    'bike gps': 'gps_tracker',
    # Headlight
    'headlight': 'headlight',
    'headlights': 'headlight',
    'motorcycle headlight': 'headlight',
    # Indicator
    'indicator': 'indicator',
    'indicators': 'indicator',
    'motorcycle indicator': 'indicator',
    'bike indicator': 'indicator',
    # Horn
    'horn': 'horn',
    'horns': 'horn',
    'motorcycle horn': 'horn',
    'bike horn': 'horn',
    # Charger (non-USB)
    'charger': 'charger',
    # Footrest
    'footrest': 'footrest',
    'footrests': 'footrest',
    'motorcycle footrest': 'footrest',
    # Alarm
    'alarm': 'alarm',
    'alarms': 'alarm',
    'bike alarm': 'alarm',
    'motorcycle alarm': 'alarm',
    # Tool Kit
    'tool kit': 'tool_kit',
    'toolkit': 'tool_kit',
    'motorcycle tool kit': 'tool_kit',
    # Polish
    'polish': 'polish',
    'bike polish': 'polish',
}

# Human-readable display names for each canonical category.
CATEGORY_DISPLAY: Dict[str, str] = {
    'helmet': 'Helmet',
    'helmet_accessories': 'Helmet Accessories',
    'gloves': 'Gloves',
    'jackets': 'Jackets',
    'riding_pants': 'Riding Pants',
    'knee_guard': 'Knee Guard',
    'ear_plugs': 'Ear Plugs',
    'phone_mount': 'Phone Mount',
    'crash_guard': 'Crash Guard',
    'leg_guard': 'Leg Guard',
    'sump_guard': 'Sump Guard',
    'radiator_guard': 'Radiator Guard',
    'fork_sliders': 'Fork Sliders',
    'frame_sliders': 'Frame Sliders',
    'pillion_grab_rail': 'Pillion Grab Rail',
    'luggage_rack': 'Luggage Rack',
    'side_stand_extender': 'Side Stand Extender',
    'handlebar_risers': 'Handlebar Risers',
    'bar_end_weights': 'Bar End Weights',
    'tank_sticker': 'Tank Sticker',
    'wheel_rim_tape': 'Wheel Rim Tape',
    'bicycle_helmet': 'Bicycle Helmet',
    'bike_cover': 'Bike Cover',
    'chain_lube': 'Chain Lube',
    'chain_cleaner': 'Chain Cleaner',
    'engine_oil': 'Engine Oil',
    'tyre_inflator': 'Tyre Inflator',
    'tank_bag': 'Tank Bag',
    'saddle_bag': 'Saddle Bag',
    'tail_bag': 'Tail Bag',
    'usb_charger': 'USB Charger',
    'disc_lock': 'Disc Lock',
    'chain_lock': 'Chain Lock',
    'action_camera': 'Action Camera',
    'dash_cam': 'Dash Cam',
    'seat_cover': 'Seat Cover',
    'handlebar_grip': 'Handlebar Grip',
    'mirror': 'Mirror',
    'windshield': 'Windshield',
    'gps_tracker': 'GPS Tracker',
    'headlight': 'Headlight',
    'indicator': 'Indicator',
    'horn': 'Horn',
    'charger': 'Charger',
    'footrest': 'Footrest',
    'alarm': 'Alarm',
    'tool_kit': 'Tool Kit',
    'polish': 'Polish',
}

# Slug for each canonical category (used in URLs).
CATEGORY_SLUGS: Dict[str, str] = {cat: cat.replace('_', '-') for cat in CANONICAL_CATEGORIES}

# Categories where we expect strong Amazon data (motorcycle accessories).
# Used by quality scoring. All snake_case.
HIGH_CONFIDENCE_CATEGORIES = {
    'helmet', 'helmet_accessories', 'phone_mount', 'chain_lube', 'chain_cleaner',
    'engine_oil', 'tyre_inflator', 'bike_cover', 'gloves',
    'jackets', 'tank_bag', 'saddle_bag', 'tail_bag',
    'usb_charger', 'disc_lock', 'chain_lock', 'knee_guard',
    'crash_guard', 'ear_plugs', 'riding_pants',
    'leg_guard', 'sump_guard', 'radiator_guard', 'fork_sliders',
    'frame_sliders', 'pillion_grab_rail', 'luggage_rack',
    'side_stand_extender', 'handlebar_risers', 'bar_end_weights',
    'tank_sticker', 'wheel_rim_tape',
}

# Categories that are universal (fit any motorcycle).
# Products in these categories get recommended for every bike.
UNIVERSAL_CATEGORIES = {
    'helmet', 'gloves', 'jackets', 'riding_pants', 'knee_guard', 'ear_plugs',
    'phone_mount', 'chain_lube', 'chain_cleaner', 'engine_oil',
    'tyre_inflator', 'bike_cover', 'tank_bag', 'saddle_bag', 'tail_bag',
    'usb_charger', 'seat_cover', 'handlebar_grip', 'mirror', 'windshield',
    'gps_tracker', 'headlight', 'indicator', 'horn', 'charger', 'footrest',
    'alarm', 'tool_kit', 'polish', 'action_camera', 'dash_cam',
    'tank_sticker', 'wheel_rim_tape',
}

# Categories that are bike-specific (need compatibility matching).
BIKE_SPECIFIC_CATEGORIES = {
    'crash_guard', 'disc_lock', 'chain_lock', 'leg_guard', 'sump_guard',
    'radiator_guard', 'fork_sliders', 'frame_sliders', 'pillion_grab_rail',
    'luggage_rack', 'side_stand_extender', 'handlebar_risers', 'bar_end_weights',
}

# Title keywords mapped to canonical categories for inference.
# Order matters: first match wins. More specific patterns first.
_CATEGORY_TITLE_KEYWORDS: List[Tuple[str, str]] = [
    # Helmet (most specific first)
    ('full face helmet', 'helmet'),
    ('modular helmet', 'helmet'),
    ('open face helmet', 'helmet'),
    ('half helmet', 'helmet'),
    ('dual visor helmet', 'helmet'),
    ('flip up helmet', 'helmet'),
    ('helmet', 'helmet'),
    ('headgear', 'helmet'),
    # Phone Mount
    ('phone mount', 'phone_mount'),
    ('phone holder', 'phone_mount'),
    ('mobile holder', 'phone_mount'),
    ('mobile mount', 'phone_mount'),
    ('handlebar mount', 'phone_mount'),
    # Chain Lube
    ('chain lube', 'chain_lube'),
    ('chain spray', 'chain_lube'),
    ('chain lubricant', 'chain_lube'),
    ('chain wax', 'chain_lube'),
    # Chain Cleaner
    ('chain cleaner', 'chain_cleaner'),
    ('chain clean', 'chain_cleaner'),
    # Engine Oil
    ('engine oil', 'engine_oil'),
    ('10w-40', 'engine_oil'),
    ('10w-50', 'engine_oil'),
    ('20w-50', 'engine_oil'),
    ('motor oil', 'engine_oil'),
    # Tyre Inflator
    ('tyre inflator', 'tyre_inflator'),
    ('tire inflator', 'tyre_inflator'),
    ('air compressor', 'tyre_inflator'),
    ('tyre pump', 'tyre_inflator'),
    ('air pump', 'tyre_inflator'),
    # Gloves
    ('riding gloves', 'gloves'),
    ('bike gloves', 'gloves'),
    ('motorcycle gloves', 'gloves'),
    ('gloves', 'gloves'),
    # Jackets
    ('riding jacket', 'jackets'),
    ('bike jacket', 'jackets'),
    ('motorcycle jacket', 'jackets'),
    ('jacket', 'jackets'),
    # Bike Cover
    ('bike cover', 'bike_cover'),
    ('motorcycle cover', 'bike_cover'),
    ('body cover', 'bike_cover'),
    ('scooter cover', 'bike_cover'),
    # Crash Guard
    ('crash guard', 'crash_guard'),
    ('engine guard', 'crash_guard'),
    ('frame slider', 'crash_guard'),
    ('crash bar', 'crash_guard'),
    # Leg Guard (separate category)
    ('leg guard', 'leg_guard'),
    # Sump Guard
    ('sump guard', 'sump_guard'),
    ('engine sump guard', 'sump_guard'),
    # Radiator Guard
    ('radiator guard', 'radiator_guard'),
    ('radiator cover', 'radiator_guard'),
    # Fork Sliders
    ('fork slider', 'fork_sliders'),
    ('fork protector', 'fork_sliders'),
    # Frame Sliders
    ('frame sliders', 'frame_sliders'),
    ('crash slider', 'frame_sliders'),
    # Pillion Grab Rail
    ('pillion grab rail', 'pillion_grab_rail'),
    ('grab rail', 'pillion_grab_rail'),
    # Luggage Rack
    ('luggage rack', 'luggage_rack'),
    ('rear rack', 'luggage_rack'),
    # Side Stand Extender
    ('side stand extender', 'side_stand_extender'),
    ('side stand', 'side_stand_extender'),
    # Handlebar Risers
    ('handlebar riser', 'handlebar_risers'),
    # Bar End Weights
    ('bar end weight', 'bar_end_weights'),
    ('handlebar weight', 'bar_end_weights'),
    # Tank Sticker / Pad
    ('tank sticker', 'tank_sticker'),
    ('tank pad', 'tank_sticker'),
    ('tank decal', 'tank_sticker'),
    # Wheel Rim Tape
    ('wheel rim tape', 'wheel_rim_tape'),
    ('rim tape', 'wheel_rim_tape'),
    ('rim sticker', 'wheel_rim_tape'),
    # Luggage
    ('tank bag', 'tank_bag'),
    ('tankbag', 'tank_bag'),
    ('saddle bag', 'saddle_bag'),
    ('saddlebag', 'saddle_bag'),
    ('pannier', 'saddle_bag'),
    ('tail bag', 'tail_bag'),
    ('rear bag', 'tail_bag'),
    # Protection
    ('knee guard', 'knee_guard'),
    ('knee pad', 'knee_guard'),
    ('knee protector', 'knee_guard'),
    # Security
    ('disc lock', 'disc_lock'),
    ('disk lock', 'disc_lock'),
    ('brake lock', 'disc_lock'),
    ('chain lock', 'chain_lock'),
    # Charger
    ('usb charger', 'usb_charger'),
    ('dual usb', 'usb_charger'),
    # Ear Plugs
    ('ear plug', 'ear_plugs'),
    ('earplug', 'ear_plugs'),
    # Riding Pants
    ('riding pants', 'riding_pants'),
    ('riding trousers', 'riding_pants'),
    # Other
    ('action camera', 'action_camera'),
    ('dash cam', 'dash_cam'),
    ('seat cover', 'seat_cover'),
    ('handlebar grip', 'handlebar_grip'),
    ('mirror', 'mirror'),
    ('windshield', 'windshield'),
    ('windscreen', 'windshield'),
    ('gps tracker', 'gps_tracker'),
    ('headlight', 'headlight'),
    ('indicator', 'indicator'),
    ('horn', 'horn'),
    ('footrest', 'footrest'),
    ('alarm', 'alarm'),
    ('tool kit', 'tool_kit'),
    ('polish', 'polish'),
]


def normalize_category(raw: str) -> str:
    """Normalize a raw category string to its canonical snake_case form.

    Lookup order:
        1. Exact match in CATEGORY_ALIASES (after lower/strip)
        2. Return original (lowered, stripped) if no alias found

    Returns canonical snake_case category, or the lowered raw string.
    """
    if not raw:
        return ''
    key = raw.strip().lower()
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    return key


def category_display(canonical: str) -> str:
    """Return the human-readable display name for a canonical category.

    Examples:
        'chain_lube' -> 'Chain Lube'
        'phone_mount' -> 'Phone Mount'
        'unknown_cat' -> 'Unknown Cat'
    """
    if canonical in CATEGORY_DISPLAY:
        return CATEGORY_DISPLAY[canonical]
    return canonical.replace('_', ' ').title()


def category_slug(canonical: str) -> str:
    """Return the URL slug for a canonical category.

    Examples:
        'chain_lube' -> 'chain-lube'
        'phone_mount' -> 'phone-mount'
    """
    return CATEGORY_SLUGS.get(canonical, canonical.replace('_', '-'))


def infer_category_from_title(title: str) -> str:
    """Infer a canonical category from a product title.

    Uses keyword matching against _CATEGORY_TITLE_KEYWORDS.
    Returns canonical category or empty string if no match.
    """
    if not title:
        return ''
    title_lower = title.lower()
    for pattern, canonical in _CATEGORY_TITLE_KEYWORDS:
        if pattern in title_lower:
            return canonical
    return ''


def classify_product_type(product: dict) -> str:
    """Classify a product as 'universal' or 'bike_specific'.

    Universal products fit any motorcycle (helmets, gloves, chain lube, etc.).
    Bike-specific products need compatibility matching (crash guards, etc.).
    """
    cat = product.get('category', '')
    if cat in BIKE_SPECIFIC_CATEGORIES:
        return 'bike_specific'
    return 'universal'


def classify_product_subcategory(product: dict) -> str:
    """Classify a product into its subcategory within the two-level taxonomy.

    Uses multiple signals in priority order:
        1. Product 'type' field (from Amazon browse / manual data)
        2. Product title keyword matching against taxonomy
        3. Product 'best_for' field keyword matching
        4. Brand heuristic (e.g., Motul → engine_oil, Bobo → phone_mount)
        5. Default subcategory for the parent category

    Returns the canonical subcategory string (snake_case).
    """
    parent_cat = product.get('category', '')
    title = (product.get('title', '') or '').lower()
    prod_type = (product.get('type', '') or '').lower()
    best_for = (product.get('best_for', '') or '').lower()
    brand = (product.get('brand', '') or '').lower()
    features = ' '.join(product.get('features', [])).lower() if product.get('features') else ''

    # Find the taxonomy entry for this parent category
    tax_key = _CATEGORY_TO_TAXONOMY.get(parent_cat, parent_cat)
    tax_entry = TAXONOMY.get(tax_key, {})

    if not tax_entry:
        # Category is not in any taxonomy parent.
        # Check if the category itself is a subcategory within a taxonomy.
        for t_parent, t_subs in TAXONOMY.items():
            if parent_cat in t_subs:
                return parent_cat
        return ''

    # Build a combined text for keyword matching
    combined = f'{prod_type} {title} {best_for} {features}'

    # Score each subcategory by keyword matches
    best_sub = ''
    best_score = 0

    for sub_name, keywords in tax_entry.items():
        score = 0
        for kw in keywords:
            # Exact phrase match (strongest)
            if kw in combined:
                if kw in prod_type:
                    score += 10
                if kw in title:
                    score += 5
                if kw in features:
                    score += 3
                if kw in best_for:
                    score += 2
            else:
                # Partial word match for multi-word keywords
                # e.g., "cleaning kit" matches "cleaning" and "kit" individually
                kw_words = kw.split()
                matched_words = sum(1 for w in kw_words if w in combined)
                if matched_words == len(kw_words):
                    # All words of the keyword appear in text (just not adjacent)
                    if any(w in prod_type for w in kw_words):
                        score += 8
                    if any(w in title for w in kw_words):
                        score += 4
                    if any(w in features for w in kw_words):
                        score += 2
                    if any(w in best_for for w in kw_words):
                        score += 1

        if score > best_score:
            best_score = score
            best_sub = sub_name

    if best_sub:
        return best_sub

    # Fallback: use type field directly if it matches a subcategory name
    if prod_type:
        type_normalized = prod_type.replace(' ', '_').replace('-', '_')
        for sub_name in tax_entry:
            if type_normalized == sub_name or type_normalized in sub_name:
                return sub_name

    # Final fallback: if category IS a subcategory name, return it directly
    if parent_cat in tax_entry:
        return parent_cat

    return ''


def normalize_product_category(product: dict) -> dict:
    """Normalize a product's category and subcategory to canonical form.

    Modifies the product dict in-place:
        - Sets product['category'] to canonical snake_case
        - Sets product['category_display'] to human-readable
        - Sets product['subcategory'] to canonical subcategory
        - Sets product['subcategory_display'] to human-readable subcategory
        - Sets product['product_type'] to 'universal' or 'bike_specific'

    Lookup order for category:
        1. Existing category field -> CATEGORY_ALIASES lookup
        2. If missing/empty -> infer from title keywords
        3. If still empty -> leave as empty string

    After initial category normalization, products may be reclassified
    if their title/type signals indicate they belong to a different
    taxonomy group (e.g., a 'helmet' that is actually a bluetooth intercom
    gets reclassified to 'helmet_accessories').

    Subcategory is determined by the two-level taxonomy classifier.

    Returns the modified product dict.
    """
    raw_cat = product.get('category', '')

    # Step 1: Normalize existing category
    canonical = normalize_category(raw_cat)

    # Step 2: Infer from title if missing
    if not canonical:
        canonical = infer_category_from_title(product.get('title', ''))

    # Step 3: Set category fields
    product['category'] = canonical
    product['category_display'] = category_display(canonical)
    product['product_type'] = classify_product_type(product)

    # Step 4: Reclassify products that got wrong parent category
    # e.g., bluetooth intercoms labeled as 'helmet' should be 'helmet_accessories'
    _reclassify_product(product)

    # Step 5: Classify subcategory using the two-level taxonomy
    subcategory = classify_product_subcategory(product)
    product['subcategory'] = subcategory
    product['subcategory_display'] = subcategory.replace('_', ' ').title() if subcategory else ''

    return product


# Keywords that signal a product is a helmet accessory, not a helmet itself.
_HELMET_ACCESSORY_KEYWORDS = [
    'bluetooth', 'intercom', 'headset', 'communication system',
    'visor', 'face shield', 'anti-fog',
    'chin mount', 'helmet camera', 'helmet cam',
    'helmet cleaner', 'visor cleaner', 'helmet wash', 'cleaning kit',
    'ear pad', 'helmet bag', 'helmet cover',
    'peak', 'sun visor',
]

# Products whose category was 'helmet' but should be reclassified.
_HELMET_ACCESSORY_TYPES = {
    'bluetooth_intercom', 'visor', 'camera', 'cleaning_kit',
}

# Standalone categories that should be reclassified into a taxonomy parent.
# Only for edge cases where the category is NOT in CANONICAL_CATEGORIES.
# Maps old flat category name -> (taxonomy_parent, subcategory).
_STANDALONE_TO_TAXONOMY = {
    'visor': ('helmet_accessories', 'visor'),
}

# ===== Strengthened classification rules =====
# Each rule uses REQUIRED, POSITIVE and NEGATIVE keyword sets so a product is
# never classified on a single ambiguous keyword. A category is only assigned
# when REQUIRED (or a strong POSITIVE) keywords are present AND no NEGATIVE
# keyword contradicts it.
#
# NEGATIVE keywords route a product AWAY from a motorcycle category:
#   - bicycle/cycle/kids helmets -> 'bicycle_helmet' (excluded from guides)
#   - fashion/winter/rain/casual jackets -> stays generic (not 'jackets')
_CATEGORY_RULES: Dict[str, Dict[str, List[str]]] = {
    'helmet': {
        'required': ['helmet'],
        'positive': ['full face', 'modular', 'open face', 'flip up', 'isi', 'dot', 'ece',
                     'motorcycle', 'rider', 'riding', 'bike'],
        'negative': ['bicycle', 'cycle helmet', 'cycling', 'kids', 'kid', 'toy', 'scooter toy',
                     'baby', 'toddler', 'child'],
    },
    'jackets': {
        'required': ['jacket'],
        'positive': ['riding', 'rider', 'motorcycle', 'motorbike', 'biker', 'ce armour',
                     'ce rated', 'armoured', 'armored', 'protective', 'abrasion'],
        'negative': ['winter', 'rain', 'fashion', 'casual', 'hoodie', 'hooded', 'denim',
                     'cotton', 'tracksuit', 'track suit', 'sweat', 'varsity', 'letterman',
                     'leather jacket fashion', 'designer'],
    },
}

# Products that match these negative-only signals are pulled OUT of the
# motorcycle taxonomy into a non-recommended category.
_NEGATIVE_RECLASSIFY = {
    'helmet': 'bicycle_helmet',
}


def _negatives_present(combined: str, negatives: List[str]) -> bool:
    """Match negatives as whole words/phrases (word boundaries) so that
    'cycle helmet' does NOT falsely match inside 'motorcycle helmet'."""
    import re
    for n in negatives:
        if re.search(r'(?:\b|\s)' + re.escape(n) + r'(?:\b|\s|$)', combined):
            return True
    return False


def is_motorcycle_helmet(product: dict) -> bool:
    """Return True only if the product is a motorcycle (rider) helmet.

    False for bicycle / cycle / kids / scooter-toy helmets.
    """
    title = (product.get('title', '') or '').lower()
    prod_type = (product.get('type', '') or '').lower()
    best_for = (product.get('best_for', '') or '').lower()
    combined = f'{title} {prod_type} {best_for}'
    rule = _CATEGORY_RULES.get('helmet', {})
    if 'helmet' not in combined:
        return False
    if _negatives_present(combined, rule.get('negative', [])):
        return False
    return True


def is_motorcycle_riding_jacket(product: dict) -> bool:
    """Return True only if the product is a motorcycle riding jacket.

    False for fashion / winter / rain / casual jackets and hoodies.
    """
    title = (product.get('title', '') or '').lower()
    prod_type = (product.get('type', '') or '').lower()
    best_for = (product.get('best_for', '') or '').lower()
    features = ' '.join(product.get('features', [])).lower() if product.get('features') else ''
    combined = f'{title} {prod_type} {best_for} {features}'
    rule = _CATEGORY_RULES.get('jackets', {})
    if 'jacket' not in combined:
        return False
    if _negatives_present(combined, rule.get('negative', [])):
        return False
    # Require at least one positive riding signal (or a clear 'riding jacket').
    if 'riding jacket' in combined or 'motorcycle jacket' in combined:
        return True
    return any(p in combined for p in rule.get('positive', []))


def _reclassify_product(product: dict) -> None:
    """Reclassify products that got the wrong parent category.

    Some products (especially bluetooth headsets, visors, helmet cameras)
    end up with category='helmet' from keyword matching, but they should
    actually be under 'helmet_accessories'.

    Also remaps standalone categories (e.g., 'visor', 'gloves') to their
    correct taxonomy parent (e.g., 'helmet_accessories', 'riding_gear').

    Modifies product dict in-place.
    """
    cat = product.get('category', '')
    title = (product.get('title', '') or '').lower()
    prod_type = (product.get('type', '') or '').lower()
    best_for = (product.get('best_for', '') or '').lower()

    combined = f'{title} {prod_type} {best_for}'

    # Step 1: Remap standalone categories to taxonomy parent
    if cat in _STANDALONE_TO_TAXONOMY:
        parent, sub = _STANDALONE_TO_TAXONOMY[cat]
        product['category'] = parent
        product['category_display'] = category_display(parent)
        # Pre-set subcategory hint (classify_product_subcategory will confirm)
        return

    # Step 1b: Pull non-motorcycle products out of the motorcycle taxonomy.
    # Bicycle / cycle / kids / scooter-toy helmets must never be 'helmet'.
    if cat == 'helmet' and not is_motorcycle_helmet(product):
        product['category'] = 'bicycle_helmet'
        product['category_display'] = category_display('bicycle_helmet')
        return
    # Fashion / winter / rain / casual jackets must never be 'jackets'.
    if cat == 'jackets' and not is_motorcycle_riding_jacket(product):
        # Demote to a generic, non-motorcycle label so they are excluded from
        # riding-jacket recommendations and guides.
        product['category'] = 'fashion_jacket'
        product['category_display'] = 'Jacket'
        return

    # Step 2: Reclassify 'helmet' products that are actually accessories
    if cat != 'helmet':
        return

    for kw in _HELMET_ACCESSORY_KEYWORDS:
        if kw in combined:
            if any(k in combined for k in ['bluetooth', 'intercom', 'headset', 'communication system', 'wireless', 'earphone']):
                product['category'] = 'helmet_accessories'
                product['category_display'] = 'Helmet Accessories'
                return
            if any(k in combined for k in ['visor', 'face shield', 'anti-fog', 'sun visor', 'peak']):
                product['category'] = 'helmet_accessories'
                product['category_display'] = 'Helmet Accessories'
                return
            if any(k in combined for k in ['chin mount', 'helmet camera', 'helmet cam']):
                product['category'] = 'helmet_accessories'
                product['category_display'] = 'Helmet Accessories'
                return
            if any(k in combined for k in ['helmet cleaner', 'visor cleaner', 'helmet wash', 'cleaning kit']):
                product['category'] = 'helmet_accessories'
                product['category_display'] = 'Helmet Accessories'
                return


# ===== Product Quality Pipeline =====

# Known brands with high trust (Indian motorcycle ecosystem)
TRUSTED_BRANDS = {
    'motul', 'shell', 'castrol', 'liqui moly', 'motorex',
    'studds', 'steelbird', 'vega', 'axor', 'ls2', 'smk', 'mt',
    'bobo', 'xtrim', 'gadgetbro', 'tribe', 'rideronomy',
    'michelin', 'bosch', 'mi', 'xiaomi',
    'tvs', 'hero', 'honda', 'yamaha', 'bajaj', 'suzuki',
    'royal enfield', 'ktm', 'harley-davidson', 'triumph',
    'scorpion', 'rst', 'alchemy', 'race dynamics', 'iron guard',
}

# Spam title patterns
SPAM_PATTERNS = [
    r'^test\b',
    r'^sample\b',
    r'^lorem ipsum',
    r'^placeholder',
    r'xxx+',
    r'!!!{3,}',
]

# Module-level dashboard storage
_last_quality_dashboard: Optional[dict] = None


def score_product_quality(product: dict) -> dict:
    """Score a product on multiple quality dimensions.

    Returns a dict with:
        total: 0-100 overall quality score
        breakdown: individual component scores
        flags: list of quality flags (warnings/reasons)
    """
    breakdown = {}
    flags = []
    total = 0

    # --- Amazon Rating (0-25 points) ---
    rating = product.get('rating', 0) or 0
    if rating >= 4.5:
        breakdown['rating'] = 25
    elif rating >= 4.0:
        breakdown['rating'] = 20
    elif rating >= 3.5:
        breakdown['rating'] = 15
        flags.append('low_rating')
    elif rating >= 3.0:
        breakdown['rating'] = 10
        flags.append('low_rating')
    elif rating > 0:
        breakdown['rating'] = 5
        flags.append('very_low_rating')
    else:
        breakdown['rating'] = 0
        flags.append('no_rating')

    # --- Review Count (0-15 points) ---
    reviews = product.get('review_count', 0) or product.get('reviews', 0) or 0
    if reviews >= 1000:
        breakdown['reviews'] = 15
    elif reviews >= 500:
        breakdown['reviews'] = 12
    elif reviews >= 100:
        breakdown['reviews'] = 8
    elif reviews >= 10:
        breakdown['reviews'] = 4
        flags.append('few_reviews')
    elif reviews > 0:
        breakdown['reviews'] = 2
        flags.append('very_few_reviews')
    else:
        breakdown['reviews'] = 0
        flags.append('no_reviews')

    # --- Product Completeness (0-20 points) ---
    completeness = 0
    if product.get('title'):
        completeness += 4
    if product.get('brand'):
        completeness += 3
    if product.get('category'):
        completeness += 3
    if product.get('compatible_bikes'):
        completeness += 3
    if product.get('best_for'):
        completeness += 3
    if product.get('verdict'):
        completeness += 2
    editor_rating = product.get('editor_rating', 0) or 0
    if editor_rating > 0:
        completeness += 2
    breakdown['completeness'] = completeness

    # --- Image (0-10 points) ---
    if product.get('image'):
        breakdown['image'] = 10
    else:
        breakdown['image'] = 0
        flags.append('no_image')

    # --- Affiliate Link (0-10 points) ---
    if product.get('affiliate_url'):
        breakdown['affiliate'] = 10
    else:
        breakdown['affiliate'] = 0
        flags.append('no_affiliate')

    # --- Brand Reputation (0-10 points) ---
    brand = (product.get('brand') or '').strip().lower()
    if brand in TRUSTED_BRANDS:
        breakdown['brand'] = 10
    elif brand:
        breakdown['brand'] = 5
    else:
        breakdown['brand'] = 0
        flags.append('unknown_brand')

    # --- Category Confidence (0-10 points) ---
    category = (product.get('category') or '').strip().lower()
    if category in HIGH_CONFIDENCE_CATEGORIES:
        breakdown['category'] = 10
    elif category:
        breakdown['category'] = 5
        flags.append('uncertain_category')
    else:
        breakdown['category'] = 0
        flags.append('no_category')

    total = sum(breakdown.values())

    return {
        'total': total,
        'breakdown': breakdown,
        'flags': flags,
    }


def auto_assign_status(product: dict) -> str:
    """Determine the appropriate status for a product based on quality.

    Rules:
        approved: quality >= 60, has image, has affiliate, rating >= 4.0
        review:   quality >= 30, has image OR affiliate, not spam
        rejected: quality < 30, or duplicate, or missing image+affiliate,
                  or spam title, or wrong category

    Returns the assigned status string.
    """
    title = (product.get('title') or '').strip()
    image = product.get('image', '')
    affiliate = product.get('affiliate_url', '')
    rating = product.get('rating', 0) or 0
    category = (product.get('category') or '').strip()

    # --- Rejection rules ---
    # Spam title
    title_lower = title.lower()
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, title_lower):
            return 'rejected'

    # Missing both image and affiliate
    if not image and not affiliate:
        return 'rejected'

    # Missing category entirely
    if not category:
        return 'rejected'

    # --- Quality scoring ---
    quality = score_product_quality(product)
    score = quality['total']

    # --- Approved: high quality, complete data ---
    if (score >= 60
            and image
            and affiliate
            and rating >= 4.0):
        return 'approved'

    # --- Review: moderate quality, some data present ---
    if score >= 30 and (image or affiliate):
        return 'review'

    # --- Rejected: everything else ---
    return 'rejected'


def run_quality_pipeline(products: list) -> tuple:
    """Run the quality pipeline on all products.

    Assigns status to each product based on quality scoring.
    Returns (updated_products, dashboard_data).

    The dashboard_data is a dict with:
        overall: {approved: N, review: N, rejected: N}
        by_category: {category: {approved: N, review: N, rejected: N}}
        flagged: list of (slug, flags) for review/rejected products
    """
    overall = {'approved': 0, 'review': 0, 'rejected': 0, 'kept': 0}
    by_category: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {'approved': 0, 'review': 0, 'rejected': 0}
    )
    flagged = []

    for product in products:
        current = product.get('status', '')

        # Only auto-assign to products that haven't been manually set
        # Keep hidden, out_of_stock, discontinued as-is
        if current in ('hidden', 'out_of_stock', 'discontinued'):
            overall['kept'] += 1
            cat = product.get('category', 'Unknown')
            by_category[cat][current] = by_category[cat].get(current, 0) + 1
            continue

        new_status = auto_assign_status(product)
        product['status'] = new_status

        overall[new_status] = overall.get(new_status, 0) + 1
        cat = product.get('category', 'Unknown')
        by_category[cat][new_status] = by_category[cat].get(new_status, 0) + 1

        if new_status in ('review', 'rejected'):
            quality = score_product_quality(product)
            flagged.append({
                'slug': product.get('slug', 'unknown'),
                'title': product.get('title', '')[:50],
                'status': new_status,
                'score': quality['total'],
                'flags': quality['flags'],
            })

    return products, {
        'overall': overall,
        'by_category': dict(by_category),
        'flagged': flagged,
    }


def print_quality_dashboard(dashboard: dict) -> None:
    """Print the quality pipeline dashboard after sync."""
    print('\n' + '=' * 60)
    print('  PRODUCT QUALITY DASHBOARD')
    print('=' * 60)

    overall = dashboard['overall']
    total = sum(overall.values())
    print(f'\n  Total: {total} products')
    print(f'    Approved: {overall.get("approved", 0)}')
    print(f'    Review:   {overall.get("review", 0)}')
    print(f'    Rejected: {overall.get("rejected", 0)}')
    if overall.get('kept', 0):
        print(f'    Kept:     {overall.get("kept", 0)} (manual overrides preserved)')

    print(f'\n  {"Category":<25s} {"Approved":>8s} {"Review":>8s} {"Rejected":>8s}')
    print(f'  {"-"*25} {"-"*8} {"-"*8} {"-"*8}')

    for cat in sorted(dashboard['by_category'].keys()):
        counts = dashboard['by_category'][cat]
        a = counts.get('approved', 0)
        r = counts.get('review', 0)
        j = counts.get('rejected', 0)
        print(f'  {cat:<25s} {a:>8d} {r:>8d} {j:>8d}')

    if dashboard['flagged']:
        print(f'\n  Flagged products ({len(dashboard["flagged"])}):')
        for item in dashboard['flagged'][:15]:
            flags_str = ', '.join(item['flags'][:3])
            print(f'    [{item["status"]:>8s}] {item["score"]:>3d} {item["slug"][:35]:<35s} ({flags_str})')
        if len(dashboard['flagged']) > 15:
            print(f'    ... and {len(dashboard["flagged"]) - 15} more')

    print('\n' + '=' * 60)


# ===== JSON Schema (for validation reference) =====

REQUIRED_TOP_LEVEL = {'asin', 'slug', 'title', 'brand', 'category', 'status'}
REQUIRED_EDITORIAL = {'score', 'pros', 'cons'}
REQUIRED_AMAZON = {'price', 'rating', 'affiliate_url'}

EDITORIAL_FIELDS = {'score', 'pros', 'cons', 'features', 'fitment_notes',
                    'recommended_for', 'notes'}
AMAZON_FIELDS = {'price', 'mrp', 'discount', 'rating', 'review_count',
                 'availability', 'affiliate_url', 'image', 'last_updated'}

# Fields that can exist at the top level alongside nested editorial/amazon.
TOP_LEVEL_FIELDS = {'asin', 'slug', 'title', 'brand', 'category', 'type',
                    'status', 'compatible_bikes', 'best_for', 'verdict'}


# ===== Loading & Flattening =====

def load_products(products_dir: Path) -> list:
    """Load all product JSON files from the products directory.

    Returns flat dicts compatible with templates and product_engine.
    Each product dict includes all fields at the top level for backward
    compatibility, plus a 'status' field for filtering.

    The flattened structure preserves:
    - amazon.price as product.price
    - amazon.rating as product.rating
    - amazon.review_count as product.reviews (legacy alias)
    - amazon.image as product.image (legacy alias)
    - editorial.score as product.editor_rating (legacy alias)
    - editorial.pros/cons as product.pros/cons (top-level)
    """
    products = []

    if not products_dir.exists():
        return products

    for filepath in sorted(products_dir.glob('*.json')):
        if filepath.suffix == '.bak':
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Failed to load {filepath.name}: {e}")
            continue

        if isinstance(raw, list):
            for item in raw:
                flat = _flatten_product(item, filepath.name)
                if flat:
                    products.append(flat)
        elif isinstance(raw, dict):
            flat = _flatten_product(raw, filepath.name)
            if flat:
                products.append(flat)

    # Run quality pipeline — auto-assign status for draft products
    products, dashboard = run_quality_pipeline(products)
    global _last_quality_dashboard
    _last_quality_dashboard = dashboard

    # Generate compact SEO slugs (replaces long Amazon-title slugs; appends
    # ASIN on collisions). Keeps internal links consistent since every
    # template resolves product URLs via product['slug'].
    regenerate_all_slugs(products)

    return products


def get_quality_dashboard() -> Optional[dict]:
    """Return the last quality pipeline dashboard, or None if not run."""
    return _last_quality_dashboard


def derive_editorial_verdict(product: dict) -> str:
    """Derive an editorial verdict label from REAL data only.

    This is the trust-preserving replacement for a fabricated numeric
    "editor score". Rules:
      * The verdict is anchored to the Amazon user rating. A product rated
        below 4.0 by customers never receives a positive editorial verdict.
      * Editorial-only labels (Budget Pick, Premium Pick, Best Value) are
        assigned only when a genuine editorial review exists (pros/cons or a
        manual verdict), so we never fabricate an opinion.
      * If no editorial review content exists, we surface only the base
        rating-derived verdict (or nothing for low-rated products).

    Returns one of the verdict label keys, or '' when nothing honest can be
    shown (caller then displays the Amazon rating alone).
    """
    rating = float(product.get('rating', 0) or 0)
    if rating <= 0:
        return ''

    has_editorial_review = bool(
        product.get('pros') or product.get('cons')
        or product.get('verdict') or product.get('editorial_notes')
        or product.get('editorial_verdict')
    )

    if rating >= 4.5:
        base = 'excellent'
    elif rating >= 4.0:
        base = 'very_good'
    elif rating >= 3.5:
        base = 'good'
    else:
        return ''

    if not has_editorial_review:
        return base

    tier = _price_tier(int(product.get('price', 0) or 0), product.get('category', ''))
    if tier in ('budget', 'value') and rating >= 4.0:
        return 'budget_pick'
    if tier in ('premium', 'high-end') and rating >= 4.3:
        return 'premium_pick'
    from product_engine import preferred_price_range
    band = preferred_price_range(product.get('category', ''))
    if rating >= 4.3 and band:
        low, high = band
        if low <= int(product.get('price', 0) or 0) <= high:
            return 'best_value'
    return base


def _price_tier(price: int, category: str) -> str:
    """Determine price tier for a product in a category."""
    from product_engine import preferred_price_range
    band = preferred_price_range(category)
    if not band:
        return 'mid-range'
    low, high = band
    if price <= low * 0.6:
        return 'budget'
    if price <= low:
        return 'value'
    if price <= high:
        return 'mid-range'
    if price <= high * 1.5:
        return 'premium'
    return 'high-end'


def _flatten_product(raw: dict, source_file: str = '') -> Optional[dict]:
    """Convert a nested product dict into a flat dict for template compat.

    Handles both formats:
    1. New nested format: editorial.score, amazon.price, etc.
    2. Legacy flat format: editor_rating, price, rating, etc.

    Returns None if the product is missing critical fields.
    """
    if not raw:
        return None

    product = {}

    # --- Top-level identity & metadata ---
    for field in TOP_LEVEL_FIELDS:
        if field in raw:
            product[field] = raw[field]

    # --- Editorial data ---
    editorial = raw.get('editorial', {})
    if editorial:
        # A real manual editorial score may exist; we never fabricate one.
        product['editor_rating'] = editorial.get('score', raw.get('editor_rating', 0))
        product['editorial_verdict'] = editorial.get('verdict_label', raw.get('editorial_verdict', ''))
        # Pros & cons (keep at top level for templates)
        product['pros'] = editorial.get('pros', raw.get('pros', []))
        product['cons'] = editorial.get('cons', raw.get('cons', []))
        # Additional editorial fields
        product['features'] = editorial.get('features', [])
        product['fitment_notes'] = editorial.get('fitment_notes', '')
        product['recommended_for'] = editorial.get('recommended_for', [])
        product['editorial_notes'] = editorial.get('notes', '')
        # Store raw editorial for validation/sync reference
        product['_editorial'] = editorial
    else:
        # Legacy flat format fallback
        product['editor_rating'] = raw.get('editor_rating', 0)
        product['editorial_verdict'] = raw.get('editorial_verdict', '')
        product['pros'] = raw.get('pros', [])
        product['cons'] = raw.get('cons', [])

    # --- Amazon data ---
    amazon = raw.get('amazon', {})
    if amazon:
        product['price'] = amazon.get('price', raw.get('price', 0))
        product['mrp'] = amazon.get('mrp', None)
        product['discount'] = amazon.get('discount', None)
        product['rating'] = amazon.get('rating', raw.get('rating', 0))
        product['reviews'] = amazon.get('review_count', raw.get('reviews', 0))
        product['review_count'] = product['reviews']  # both keys work
        product['availability'] = amazon.get('availability', '')
        product['affiliate_url'] = amazon.get('affiliate_url', raw.get('affiliate_url', ''))
        product['image'] = amazon.get('image', raw.get('image', ''))
        product['amazon_image_url'] = amazon.get('image', raw.get('image', ''))
        product['last_updated'] = amazon.get('last_updated', None)
        product['amazon_synced'] = bool(amazon.get('last_updated'))
        # Store raw amazon for sync engine reference
        product['_amazon'] = amazon
    else:
        # Legacy flat format fallback
        product['price'] = raw.get('price', 0)
        product['mrp'] = raw.get('mrp', None)
        product['discount'] = raw.get('discount', None)
        product['rating'] = raw.get('rating', 0)
        product['reviews'] = raw.get('reviews', 0)
        product['review_count'] = product['reviews']
        product['availability'] = raw.get('availability', '')
        product['affiliate_url'] = raw.get('affiliate_url', '')
        product['image'] = raw.get('image', '')
        product['amazon_image_url'] = raw.get('image', raw.get('amazon_image_url', ''))
        product['last_updated'] = None
        product['amazon_synced'] = False

    # --- Compatibility ---
    product['compatible_bikes'] = raw.get('compatible_bikes', ['*'])

    # --- Presentation ---
    product['best_for'] = raw.get('best_for', '')
    product['verdict'] = raw.get('verdict', '')

    # --- Editorial verdict (derived from real data; never fabricated) ---
    # Respect a manually set verdict label if present in the source, otherwise
    # derive one from the Amazon rating + any genuine editorial review content.
    if not product.get('editorial_verdict'):
        product['editorial_verdict'] = derive_editorial_verdict(product)

    # --- Status (default to 'approved' for legacy compat) ---
    product['status'] = raw.get('status', 'approved')

    # --- Category normalization (canonical snake_case) ---
    normalize_product_category(product)

    # --- Source tracking ---
    product['_source_file'] = source_file

    return product


def unflatten_product(product: dict) -> dict:
    """Convert a flat product dict back to the nested JSON structure.

    Used when saving products back to JSON files. Strips internal keys
    (those starting with '_').
    """
    nested = {
        'asin': product.get('asin', ''),
        'slug': product.get('slug', ''),
        'title': product.get('title', ''),
        'brand': product.get('brand', ''),
        'category': product.get('category', ''),
        'type': product.get('type', ''),
        'status': product.get('status', 'approved'),
        'editorial': {
            'score': product.get('editor_rating', 0),
            'verdict_label': product.get('editorial_verdict', ''),
            'pros': product.get('pros', []),
            'cons': product.get('cons', []),
            'features': product.get('features', []),
            'fitment_notes': product.get('fitment_notes', ''),
            'recommended_for': product.get('recommended_for', []),
            'notes': product.get('editorial_notes', ''),
        },
        'amazon': {
            'price': product.get('price', 0),
            'mrp': product.get('mrp'),
            'discount': product.get('discount'),
            'rating': product.get('rating', 0),
            'review_count': product.get('review_count', product.get('reviews', 0)),
            'availability': product.get('availability', ''),
            'affiliate_url': product.get('affiliate_url', ''),
            'image': product.get('image', ''),
            'last_updated': product.get('last_updated'),
        },
        'compatible_bikes': product.get('compatible_bikes', ['*']),
        'best_for': product.get('best_for', ''),
        'verdict': product.get('verdict', ''),
    }
    return nested


# ===== Filtering =====

def approved_products(products: list) -> list:
    """Return only products with status == 'approved'."""
    return [p for p in products if p.get('status') == 'approved']


def active_products(products: list) -> list:
    """Return products that should appear on the website.

    Includes: approved, out_of_stock (shown with availability badge)
    Excludes: draft, hidden, discontinued
    """
    return [p for p in products if p.get('status') in WEBSITE_STATUSES]


def recommendable_products(products: list) -> list:
    """Return products the recommendation engine should process.

    Only 'approved' products are recommendable.
    """
    return [p for p in products if p.get('status') in RECOMMENDABLE_STATUSES]


def products_by_status(products: list) -> Dict[str, list]:
    """Group products by their status."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        status = p.get('status', 'unknown')
        groups[status].append(p)
    return dict(groups)


def products_by_category(products: list) -> Dict[str, list]:
    """Group products by their category."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        cat = p.get('category', 'Other')
        groups[cat].append(p)
    return dict(groups)


def products_by_brand(products: list) -> Dict[str, list]:
    """Group products by their brand."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        brand = p.get('brand', 'Unknown')
        groups[brand].append(p)
    return dict(groups)


# ===== Validation =====

def validate_products(products: list) -> dict:
    """Validate the entire product library.

    Checks:
    - Duplicate ASINs
    - Missing affiliate links (approved products)
    - Missing images (approved products)
    - Invalid prices (negative, zero for approved)
    - Missing categories
    - Missing editorial info (pros, cons, score)
    - Empty compatible_bikes
    - Unknown status values

    Returns: {errors: [...], warnings: [...], stats: {...}}
    """
    errors = []
    warnings = []
    asin_index: Dict[str, list] = defaultdict(list)
    slug_index: Dict[str, list] = defaultdict(list)

    for i, p in enumerate(products):
        slug = p.get('slug', f'product_{i}')
        asin = (p.get('asin') or '').strip().upper()
        status = p.get('status', 'approved')
        source = p.get('_source_file', 'unknown')

        # --- Required fields ---
        if not p.get('slug'):
            errors.append(f"[{source}] Product at index {i}: missing 'slug'")
        if not p.get('title'):
            errors.append(f"[{source}] {slug}: missing 'title'")
        if not p.get('brand'):
            warnings.append(f"[{source}] {slug}: missing 'brand'")
        if not p.get('category'):
            errors.append(f"[{source}] {slug}: missing 'category'")

        # --- Status ---
        if status not in VALID_STATUSES:
            errors.append(f"[{source}] {slug}: invalid status '{status}' "
                         f"(must be one of: {', '.join(sorted(VALID_STATUSES))})")

        # --- ASIN tracking ---
        if asin:
            asin_index[asin].append(slug)

        # --- Slug tracking ---
        if p.get('slug'):
            slug_index[p['slug']].append(source)

        # --- Approved product quality checks ---
        if status == 'approved':
            # Affiliate link
            if not p.get('affiliate_url'):
                warnings.append(f"[{source}] {slug}: approved product missing affiliate URL")

            # Image
            if not p.get('image'):
                warnings.append(f"[{source}] {slug}: approved product missing image")

            # Price
            price = p.get('price', 0)
            if price < 0:
                errors.append(f"[{source}] {slug}: negative price ({price})")
            if price == 0:
                warnings.append(f"[{source}] {slug}: price is 0 (may be unavailable)")

            # Editorial
            if not p.get('pros'):
                warnings.append(f"[{source}] {slug}: missing 'pros' in editorial data")
            if not p.get('cons'):
                warnings.append(f"[{source}] {slug}: missing 'cons' in editorial data")
            if not p.get('editor_rating'):
                warnings.append(f"[{source}] {slug}: missing editor rating/score")

            # Compatibility
            compat = p.get('compatible_bikes', [])
            if not compat:
                warnings.append(f"[{source}] {slug}: empty compatible_bikes list")

    # --- Duplicate detection ---
    for asin, slugs in asin_index.items():
        if len(slugs) > 1:
            errors.append(f"Duplicate ASIN {asin}: found in {', '.join(slugs)}")

    for slug, sources in slug_index.items():
        if len(sources) > 1:
            errors.append(f"Duplicate slug '{slug}': found in {', '.join(sources)}")

    # --- Stats ---
    by_status = defaultdict(int)
    by_category = defaultdict(int)
    by_brand = defaultdict(int)
    for p in products:
        by_status[p.get('status', 'unknown')] += 1
        by_category[p.get('category', 'Unknown')] += 1
        by_brand[p.get('brand', 'Unknown')] += 1
    stats = {
        'total': len(products),
        'by_status': dict(by_status),
        'by_category': dict(by_category),
        'by_brand': dict(by_brand),
    }

    return {
        'errors': errors,
        'warnings': warnings,
        'stats': stats,
        'valid': len(errors) == 0,
    }


def find_duplicates(products: list) -> dict:
    """Find duplicate products by ASIN, slug, or normalized title.

    Returns: {asin_duplicates: [...], slug_duplicates: [...], title_duplicates: [...]}
    """
    asin_index: Dict[str, list] = defaultdict(list)
    slug_index: Dict[str, list] = defaultdict(list)
    title_index: Dict[str, list] = defaultdict(list)

    for p in products:
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            asin_index[asin].append(p.get('slug', 'unknown'))

        slug = (p.get('slug') or '').strip().lower()
        if slug:
            slug_index[slug].append(p.get('_source_file', 'unknown'))

        title = (p.get('title') or '').strip().lower()
        if title:
            title_index[title].append(p.get('slug', 'unknown'))

    asin_dupes = [{'asin': a, 'products': s} for a, s in asin_index.items() if len(s) > 1]
    slug_dupes = [{'slug': s, 'sources': src} for s, src in slug_index.items() if len(src) > 1]
    title_dupes = [{'title': t, 'products': s} for t, s in title_index.items() if len(s) > 1]

    return {
        'asin_duplicates': asin_dupes,
        'slug_duplicates': slug_dupes,
        'title_duplicates': title_dupes,
    }


# ===== Statistics =====

def generate_stats(products: list) -> dict:
    """Generate comprehensive product library statistics."""
    by_status = defaultdict(int)
    by_category = defaultdict(int)
    by_brand = defaultdict(int)

    stats = {
        'total_products': len(products),
        'average_rating': 0.0,
        'average_discount': 0.0,
        'average_price': 0.0,
        'average_editor_rating': 0.0,
        'out_of_stock_count': 0,
        'draft_count': 0,
        'discontinued_count': 0,
        'hidden_count': 0,
        'missing_editorial': [],
        'missing_images': [],
        'missing_affiliate': [],
        'duplicate_asins': [],
        'categories_empty': [],
        'products_with_compatibility': 0,
        'universal_products': 0,
    }

    if not products:
        return stats

    ratings = []
    discounts = []
    prices = []
    editor_ratings = []
    asin_seen: Dict[str, list] = defaultdict(list)

    for p in products:
        status = p.get('status', 'unknown')
        category = p.get('category', 'Unknown')
        brand = p.get('brand', 'Unknown')
        slug = p.get('slug', 'unknown')

        by_status[status] += 1
        by_category[category] += 1
        by_brand[brand] += 1

        if status == 'out_of_stock':
            stats['out_of_stock_count'] += 1
        elif status == 'draft':
            stats['draft_count'] += 1
        elif status == 'discontinued':
            stats['discontinued_count'] += 1
        elif status == 'hidden':
            stats['hidden_count'] += 1

        # Ratings
        r = p.get('rating', 0)
        if r:
            ratings.append(float(r))

        er = p.get('editor_rating', 0)
        if er:
            editor_ratings.append(float(er))

        # Price
        price = p.get('price', 0)
        if price:
            prices.append(float(price))

        # Discount
        disc = p.get('discount', 0)
        if disc:
            discounts.append(float(disc))

        # Missing data
        if not p.get('pros') and not p.get('cons'):
            stats['missing_editorial'].append(slug)
        if not p.get('image'):
            stats['missing_images'].append(slug)
        if not p.get('affiliate_url'):
            stats['missing_affiliate'].append(slug)

        # Compatibility
        compat = p.get('compatible_bikes', [])
        if compat:
            stats['products_with_compatibility'] += 1
            if '*' in compat:
                stats['universal_products'] += 1

        # ASIN tracking
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            asin_seen[asin].append(slug)

    # Averages
    if ratings:
        stats['average_rating'] = round(sum(ratings) / len(ratings), 2)
    if editor_ratings:
        stats['average_editor_rating'] = round(sum(editor_ratings) / len(editor_ratings), 2)
    if prices:
        stats['average_price'] = round(sum(prices) / len(prices), 0)
    if discounts:
        stats['average_discount'] = round(sum(discounts) / len(discounts), 1)

    # Duplicates
    stats['duplicate_asins'] = [
        {'asin': a, 'products': s} for a, s in asin_seen.items() if len(s) > 1
    ]

    # Final grouping stats
    stats['by_status'] = dict(by_status)
    stats['by_category'] = dict(by_category)
    stats['by_brand'] = dict(by_brand)

    return stats


# ===== Import/Export =====

def import_legacy_products(products_dir: Path, dry_run: bool = False) -> dict:
    """Migrate old flat JSON files to the new nested structure.

    Reads each .json file in products_dir, converts products from flat format
    to the new nested format, and saves them back.

    Returns: {migrated: int, files: [...], errors: [...]}
    """
    result = {'migrated': 0, 'files': [], 'errors': []}

    if not products_dir.exists():
        result['errors'].append(f"Directory not found: {products_dir}")
        return result

    for filepath in sorted(products_dir.glob('*.json')):
        if filepath.suffix == '.bak':
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            result['errors'].append(f"Failed to read {filepath.name}: {e}")
            continue

        if not isinstance(raw, list):
            result['errors'].append(f"{filepath.name}: expected array, got {type(raw).__name__}")
            continue

        migrated_products = []
        for item in raw:
            nested = _migrate_legacy_product(item)
            migrated_products.append(nested)
            result['migrated'] += 1

        if not dry_run:
            # Create backup
            backup_path = filepath.with_suffix('.json.bak')
            shutil.copy2(filepath, backup_path)

            # Write migrated data
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(migrated_products, f, indent=2, ensure_ascii=False)

        result['files'].append(filepath.name)

    return result


def _migrate_legacy_product(raw: dict) -> dict:
    """Convert a legacy flat product dict to the new nested structure."""
    # Determine status - default to 'approved' for existing products
    status = raw.get('status', 'approved')

    # Build editorial section
    editorial = {
        'score': raw.get('editor_rating', 0),
        'pros': raw.get('pros', []),
        'cons': raw.get('cons', []),
        'features': raw.get('features', []),
        'fitment_notes': raw.get('fitment_notes', ''),
        'recommended_for': raw.get('recommended_for', []),
        'notes': raw.get('editorial_notes', ''),
    }

    # Build amazon section
    amazon = {
        'price': raw.get('price', 0),
        'mrp': raw.get('mrp'),
        'discount': raw.get('discount'),
        'rating': raw.get('rating', 0),
        'review_count': raw.get('reviews', raw.get('review_count', 0)),
        'availability': raw.get('availability', ''),
        'affiliate_url': raw.get('affiliate_url', ''),
        'image': raw.get('image', ''),
        'last_updated': raw.get('last_updated'),
    }

    return {
        'asin': raw.get('asin', ''),
        'slug': raw.get('slug', ''),
        'title': raw.get('title', ''),
        'brand': raw.get('brand', ''),
        'category': raw.get('category', ''),
        'type': raw.get('type', ''),
        'status': status,
        'editorial': editorial,
        'amazon': amazon,
        'compatible_bikes': raw.get('compatible_bikes', ['*']),
        'best_for': raw.get('best_for', ''),
        'verdict': raw.get('verdict', ''),
    }


def export_products(products: list, output_path: Path) -> None:
    """Export products to a JSON file (for backup/sharing).

    Converts flat dicts back to nested format for clean export.
    """
    nested = [unflatten_product(p) for p in products]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(nested, f, indent=2, ensure_ascii=False)


# ===== Product Lookup =====

def find_product_by_slug(products: list, slug: str) -> Optional[dict]:
    """Find a product by its slug."""
    for p in products:
        if p.get('slug') == slug:
            return p
    return None


def find_product_by_asin(products: list, asin: str) -> Optional[dict]:
    """Find a product by its ASIN."""
    asin_upper = asin.strip().upper()
    for p in products:
        if (p.get('asin') or '').strip().upper() == asin_upper:
            return p
    return None


def find_products_by_asin(products: list, asins: list) -> list:
    """Find multiple products by their ASINs."""
    asin_set = {a.strip().upper() for a in asins}
    return [p for p in products if (p.get('asin') or '').strip().upper() in asin_set]


# ===== Product Count Management =====

def count_by_status(products: list) -> Dict[str, int]:
    """Count products by status."""
    counts: Dict[str, int] = defaultdict(int)
    for p in products:
        counts[p.get('status', 'unknown')] += 1
    return dict(counts)


def count_by_category(products: list) -> Dict[str, int]:
    """Count products by category."""
    counts: Dict[str, int] = defaultdict(int)
    for p in products:
        counts[p.get('category', 'Unknown')] += 1
    return dict(counts)


# ===== Import Helpers =====

# Brand normalization map: lowercase canonical -> display name
BRAND_DISPLAY_NAMES: Dict[str, str] = {
    'bobo': 'BOBO',
    'studds': 'Studds',
    'steelbird': 'Steelbird',
    'vega': 'Vega',
    'axor': 'Axor',
    'ls2': 'LS2',
    'smk': 'SMK',
    'mt': 'MT',
    'motul': 'Motul',
    'shell': 'Shell',
    'castrol': 'Castrol',
    'liqui moly': 'Liqui Moly',
    'motorex': 'Motorex',
    'michelin': 'Michelin',
    'bosch': 'Bosch',
    'amazon basics': 'Amazon Basics',
    'amazonbasics': 'Amazon Basics',
    'tvs': 'TVS',
    'hero': 'Hero MotoCorp',
    'honda': 'Honda',
    'yamaha': 'Yamaha',
    'bajaj': 'Bajaj',
    'suzuki': 'Suzuki',
    'royal enfield': 'Royal Enfield',
    'ktm': 'KTM',
    'harley-davidson': 'Harley-Davidson',
    'triumph': 'Triumph',
    'xiaomi': 'Xiaomi',
    'strief': 'STRIFF',
}

def generate_slug(title: str) -> str:
    """Generate a short, SEO-friendly slug from a product title.

    Creates slugs of 3-6 meaningful words by:
        1. Stripping generic/stop words (motorcycle, bike, helmet, premium, etc.)
        2. Keeping brand names, model numbers, and product-specific terms
        3. Limiting to 3-6 meaningful words
        4. Appending ASIN on duplicates (handled externally by resolve_slug_duplicates)

    Examples:
        'Vega Ranger DX Crew Full Face Motorcycle Helmet' -> 'vega-ranger-dx'
        'SMK Stellar Sports Full Face Helmet' -> 'smk-stellar-sports'
        'Motul C2 Chain Lube 150ml' -> 'motul-c2-chain-lube'
        'BOBO BM4 PRO Plus Jaw-Grip Phone Mount' -> 'bobo-bm4-pro-plus'
    """
    import re

    # Generic words to strip (case-insensitive)
    STOP_WORDS = {
        # Product category generic
        'motorcycle', 'bike', 'biking', 'helmet', 'riding', 'gloves',
        'jacket', 'pants', 'boots', 'visor', 'cover', 'mount', 'holder',
        # Descriptors
        'premium', 'comfortable', 'lightweight', 'heavy', 'duty', 'strong',
        'sturdy', 'durable', 'tough', 'best', 'top', 'new', 'original',
        'professional', 'advanced', 'super', 'ultra', 'max', 'mini',
        'classic', 'standard', 'basic', 'essential', 'universal',
        'portable', 'electric', 'digital', 'automatic', 'manual',
        # Helmet/face specific
        'full', 'face', 'half', 'open', 'flip', 'up', 'modular',
        'visor', 'shield', 'visor',
        # Product variant suffixes
        'plus', 'pro', 'lite', 'light', 'edition', 'version',
        # Material/feature
        'interior', 'shock', 'absorbing', 'absorber', 'waterproof',
        'breathable', 'anti', 'skid', 'scratch', 'resistant', 'proof',
        'mesh', 'fabric', 'leather', 'nylon', 'polyester', 'steel',
        'carbon', 'fiber', 'glass',
        # Engine/maintenance generic
        'engine', 'oil', 'lube', 'chain', 'cleaner', 'brake',
        # Compatibility
        'compatible', 'compatibility', 'fits', 'fitting', 'suitable',
        'with', 'for', 'the', 'and', 'or', 'of', 'in', 'on', 'to',
        'a', 'an', 'is', 'it', 'by', 'from', 'at', 'as', 'be',
        # Sizes/variants
        'size', 'small', 'medium', 'large', 'xl', 'xxl', 'xxxl',
        'one', 'two', 'three', 'set', 'pack',
        # Wall/mount generic
        'wall', 'mounted', 'standing', 'fixed',
        # Misc filler
        'all', 'every', 'each', 'any', 'no', 'not', 'very', 'more',
        'most', 'less', 'least', 'also', 'too', 'just', 'only',
        'easy', 'simple', 'quick', 'fast', 'high', 'low', 'extra',
        'certified', 'grade', 'type', 'style', 'design',
    }

    slug = title.lower().strip()

    # Remove non-alphanumeric except hyphens and spaces
    slug = re.sub(r'[^a-z0-9\s-]', ' ', slug)

    # Split into words (split on spaces AND hyphens)
    words = re.split(r'[\s-]+', slug)

    # Filter out stop words and very short tokens
    meaningful = []
    for w in words:
        w_clean = w.strip('-')
        if len(w_clean) < 2:
            continue
        if w_clean in STOP_WORDS:
            continue
        # Skip pure color words unless they look like a model variant
        if w_clean in {'black', 'white', 'red', 'blue', 'grey', 'gray', 'green', 'orange', 'yellow', 'pink', 'silver', 'golden'}:
            continue
        meaningful.append(w_clean)

    # Take first 3-6 meaningful words
    result_words = meaningful[:6]

    # Ensure at least 3 words if possible
    if len(result_words) < 3 and len(meaningful) >= 3:
        result_words = meaningful[:3]

    # Build slug
    slug = '-'.join(result_words) if result_words else re.sub(r'[^a-z0-9]', '', title.lower().strip())[:20]

    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')

    return slug


def resolve_slug_duplicates(products: list) -> None:
    """Resolve duplicate slugs by appending ASIN.

    Scans all products and appends ASIN suffix to any slug that
    would cause a duplicate. Modifies product dicts in-place.
    """
    slug_counts: Dict[str, int] = {}
    slug_products: Dict[str, list] = defaultdict(list)

    # First pass: count occurrences of each slug
    for p in products:
        slug = (p.get('slug') or '').strip().lower()
        if slug:
            slug_counts[slug] = slug_counts.get(slug, 0) + 1
            slug_products[slug].append(p)

    # Second pass: append ASIN to duplicates
    for slug, prods in slug_products.items():
        if len(prods) <= 1:
            continue
        for p in prods:
            asin = (p.get('asin') or '').strip()
            if asin:
                p['slug'] = f'{slug}-{asin}'


def regenerate_all_slugs(products: list) -> int:
    """Regenerate compact SEO slugs for every product.

    Every product gets a short slug (brand + model + key terms, capped at a
    few words) so URLs stay clean and consistent. On slug collisions the ASIN
    is appended (handled by resolve_slug_duplicates).

    Returns the number of slugs regenerated.
    """
    regenerated = 0
    for p in products:
        new_slug = generate_slug(p.get('title', ''))
        if new_slug and new_slug != p.get('slug'):
            p['slug'] = new_slug
            regenerated += 1

    # Resolve any duplicates by appending ASIN
    resolve_slug_duplicates(products)

    return regenerated


def normalize_brand(brand: str) -> str:
    """Normalize a brand name to its canonical display form.

    Examples:
        'bobo' -> 'BOBO'
        'studds' -> 'Studds'
        'TVS' -> 'TVS'
    """
    if not brand:
        return brand
    key = brand.strip().lower()
    return BRAND_DISPLAY_NAMES.get(key, brand.strip().title())


def is_empty_or_default(value: Any) -> bool:
    """Check if a value is empty or a default/placeholder value.

    Used to decide whether to generate content for a field.
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ('', 'N/A', 'TBD', 'TODO'):
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    return False
