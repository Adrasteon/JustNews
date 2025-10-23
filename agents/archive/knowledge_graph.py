from common.observability import get_logger

#!/usr/bin/env python3
"""
Phase 3: Knowledge Graph Foundation

Initial implementation of knowledge graph infrastructure for research-scale archiving.
This module establishes the foundation for Phase 3 comprehensive knowledge graph integration.

PHASE 3 GOALS:
- Entity extraction and linking from archived articles
- Temporal knowledge graph with time-aware relationships
- Knowledge graph storage and querying capabilities
- Integration with archive storage system
"""

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import networkx as nx

from agents.archive.entity_linker import EntityLinkerManager

logger = get_logger(__name__)

class AdvancedEntityExtractor:
    """
    Advanced entity extraction with disambiguation and clustering capabilities

    Features:
    - Pattern-based entity extraction with enhanced patterns
    - Similarity-based entity disambiguation
    - Context-aware entity validation
    - Confidence scoring for extracted entities
    - Entity clustering for grouping similar entities
    """

    def __init__(self):
        # Enhanced entity patterns with better coverage and multi-language support
        self.entity_patterns = {
            'PERSON': [
                # English patterns
                re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'),  # Basic name pattern
                re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof|President|Prime\s+Minister|CEO|Chairman|Director|Senator|Governor|Mayor|Ambassador)\.?\s+[A-Z][a-z]+\b'),  # Titles
                re.compile(r'\b[A-Z][a-z]+\s+[A-Z]\.\s*[A-Z][a-z]+\b'),  # First M. Last
                re.compile(r'\b[A-Z][a-z]+\s+(?:Jr|Sr|II|III|IV)\.?\b'),  # Name with suffix
                # Spanish patterns
                re.compile(r'\b[A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)?)\b'),  # Spanish names
                # French patterns
                re.compile(r'\b[A-Z][a-zàâäéèêëïîôöùûüÿç]+(?:\s+[A-Z][a-zàâäéèêëïîôöùûüÿç]+(?:\s+[A-Z][a-zàâäéèêëïîôöùûüÿç]+)?)\b'),  # French names
            ],
            'ORG': [
                # English patterns
                re.compile(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*(?:\s+(?:Inc|Corp|LLC|Ltd|Co|Company|Corporation|Group|Association|Foundation|Institute|University|College|School|Hospital|Center|Agency|Department|Ministry|Government|Council|Committee|Board|Commission|Bank|Media|News|Press|Services|Systems|Technologies|International|Global|National|Federal|State|City|County))\b'),
                re.compile(r'\b(?:The\s+)?[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s+(?:of\s+[A-Z][a-zA-Z]+|University|College|Institute|Foundation|Corporation|Company|Group|Association|Council|Committee|Board|Commission)\b'),
                re.compile(r'\b(?:BBC|Reuters|CNN|Fox|NBC|ABC|CBS|NPR|AP|AFP|UPI|NATO|UN|EU|WHO|WTO|IMF|World\s+Bank|FBI|CIA|NSA|IRS|FDA|FAA|NASA|DARPA|NIH|CDC|FEMA)\b'),  # Known organizations and acronyms
                # International patterns
                re.compile(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s+(?:AG|GmbH|BV|NV|SAS|SARL|SL|SA|PLC|Limited|Incorporated|Corporation)\b'),  # European company suffixes
            ],
            'GPE': [
                # Major cities worldwide
                re.compile(r'\b(?:London|Paris|Berlin|Moscow|Beijing|Tokyo|Washington|New\s+York|Los\s+Angeles|Chicago|Miami|Boston|Seattle|San\s+Francisco|Austin|Dallas|Houston|Atlanta|Miami|Denver|Phoenix|Las\s+Vegas|Portland|Salt\s+Lake\s+City|Albuquerque|Sacramento|Honolulu|Anchorage|Juneau|Boise|Cheyenne|Denver|Des\s+Moines|Dover|Dover|Frankfort|Atlanta|Miami|Jackson|Jefferson\s+City|Helena|Lincoln|Concord|Trenton|Santa\s+Fe|Albany|Austin|Baton\s+Rouge|Columbia|Pierre|Nashville|Salt\s+Lake\s+City|Montpelier|Richmond|Olympia|Charleston|Madison|Cheyenne)\b'),
                # Countries
                re.compile(r'\b(?:United\s+Kingdom|United\s+States|Great\s+Britain|England|Scotland|Wales|Northern\s+Ireland|Canada|Australia|Germany|France|Italy|Spain|Japan|China|Russia|India|Brazil|Mexico|Argentina|South\s+Africa|Egypt|Turkey|Saudi\s+Arabia|Iran|Iraq|Afghanistan|Pakistan|Bangladesh|Indonesia|Philippines|Vietnam|Thailand|Malaysia|Singapore|South\s+Korea|North\s+Korea|Taiwan|Mongolia|Kazakhstan|Uzbekistan|Turkmenistan|Azerbaijan|Georgia|Armenia|Ukraine|Belarus|Poland|Czech\s+Republic|Slovakia|Hungary|Austria|Switzerland|Netherlands|Belgium|Luxembourg|Denmark|Sweden|Norway|Finland|Iceland|Ireland|Portugal|Greece|Bulgaria|Romania|Serbia|Croatia|Bosnia|Montenegro|Kosovo|Albania|Macedonia|Slovenia|Estonia|Latvia|Lithuania|Moldova|Cyprus|Malta)\b'),
                # US States
                re.compile(r'\b(?:California|Texas|Florida|New\s+York|Pennsylvania|Illinois|Ohio|Georgia|North\s+Carolina|Michigan|New\s+Jersey|Virginia|Washington|Arizona|Massachusetts|Tennessee|Indiana|Maryland|Missouri|Wisconsin|Colorado|Minnesota|South\s+Carolina|Alabama|Louisiana|Kentucky|Oregon|Oklahoma|Connecticut|Utah|Iowa|Nevada|Arkansas|Mississippi|Puerto\s+Rico|Kansas|New\s+Mexico|Nebraska|Idaho|West\s+Virginia|Hawaii|New\s+Hampshire|Maine|Rhode\s+Island|Montana|Delaware|South\s+Dakota|North\s+Dakota|Alaska|Vermont|Wyoming)\b'),
                # Spanish cities/countries
                re.compile(r'\b(?:Madrid|Barcelona|Valencia|Sevilla|Zaragoza|Bilbao|Granada|Málaga|Murcia|Palma|Las\s+Palmas|Tenerife|Santa\s+Cruz|Santiago|Vigo|Córdoba|Hospitalet|Granada|Oviedo|Badalona|Cartagena|Terrassa|Jerez|Sevilla|Sabadell|Móstoles|Santa\s+Coloma|Alcalá|Pamplona|Donostia|Fuenlabrada|Leganés|Santander|Almería|Castellón|Logroño|Salamanca|Albacete|Getafe|San\s+Sebastián|Huelva|Parla|Torrente|Marbella|Reus|Tarragona|Manresa|Rubí|Viladecans|Castelldefensa|Gavà|Mollet|Esplugues|Sant\s+Boi|Sant\s+Cugat|Sant\s+Feliu|Sant\s+Vicenç|Sant\s+Just|Cornellà|El\s+Prat|Sant\s+Adrià|Badia\s+del\s+Vallès|Ripollet|Montcada|Terrassa|Vilassar|Premià|Molins|Castellar|Polinyà|Sant\s+Quirze|Rubí|Viladecans|Castelldefensa|Gavà|Mollet|Esplugues|Sant\s+Boi|Sant\s+Cugat|Sant\s+Feliu|Sant\s+Vicenç|Sant\s+Just|Cornellà|El\s+Prat|Sant\s+Adrià|Badia\s+del\s+Vallès|Ripollet|Montcada|Terrassa|Vilassar|Premià|Molins|Castellar|Polinyà|Sant\s+Quirze)\b'),
                # French cities
                re.compile(r'\b(?:Paris|Marseille|Lyon|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|Rennes|Reims|Le\s+Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Nîmes|Saint-Denis|Clermont-Ferrand|Aix-en-Provence|Le\s+Mans|Brest|Tours|Limoges|Amiens|Metz|Perpignan|Besançon|Orléans|Mulhouse|Rouen|Caen|Nancy|Saint-Paul|Saint-Pierre|Fort-de-France|Pointe-à-Pitre|Cayenne|Saint-Denis|Basse-Terre|Saint-Barthélemy|Saint-Martin|Nouvelle-Calédonie|Polynésie|Wallis-et-Futuna|Saint-Pierre-et-Miquelon|Mayotte|Terres\s+australes\s+et\s+antarctiques\s+françaises)\b'),
            ],
            'EVENT': [
                re.compile(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*(?:\s+(?:Summit|Conference|Meeting|Election|War|Disaster|Festival|Olympics|World\s+Cup|Championships?|Tournament|Ceremony|Awards?|Prize|Nobel|Pulitzer|Oscar|Games|Cup|Final|Series|Convention|Exhibition|Expo|Fair|Show|Contest|Competition|Race|Marathon|Parade|Protest|Rally|March|Strike|Boycott|Embargo|Sanctions|Accord|Treaty|Pact|Agreement|Deal|Partnership|Alliance|Coalition|Union|Federation|Organization|Association|Council|Commission|Committee|Board|Panel|Forum|Dialogue|Talks|Negotiations|Peace|War|Battle|Siege|Invasion|Occupation|Revolution|Uprising|Coup|Assassination|Murder|Attack|Bombing|Shooting|Hijacking|Kidnapping|Hostage|Crisis|Emergency|Disaster|Earthquake|Tsunami|Hurricane|Tornado|Flood|Drought|Fire|Explosion|Accident|Crash|Collision|Incident|Scandal|Corruption|Bribery|Fraud|Embezzlement|Money\s+Laundering|Tax\s+Evasion|Insider\s+Trading|Ponzi\s+Scheme|Pyramid\s+Scheme))\b'),
                re.compile(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s+\d{4}\b'),  # Events with years
                re.compile(r'\b\d{4}\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b'),  # Years followed by event names
            ],
            'MONEY': [
                re.compile(r'\$\d+(?:,\d{3})*(?:\.\d{2})?'),  # US dollars
                re.compile(r'€\d+(?:,\d{3})*(?:\.\d{2})?'),  # Euros
                re.compile(r'£\d+(?:,\d{3})*(?:\.\d{2})?'),  # British pounds
                re.compile(r'¥\d+(?:,\d{3})*(?:\.\d{2})?'),  # Japanese yen
                re.compile(r'\d+(?:,\d{3})*(?:\.\d{2})?\s+(?:dollars?|euros?|pounds?|yen|USD|EUR|GBP|JPY|million|billion|trillion)'),  # Amounts with currency words
            ],
            'DATE': [
                re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'),  # Full dates
                re.compile(r'\b\d{1,2}/\d{1,2}/\d{4}\b'),  # MM/DD/YYYY
                re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),  # YYYY-MM-DD
                re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'),  # Days with dates
            ],
            'TIME': [
                re.compile(r'\b\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?\b'),  # HH:MM AM/PM
                re.compile(r'\b\d{1,2}\s*(?:[AaPp][Mm])\b'),  # H AM/PM
                re.compile(r'\b\d{1,2}:\d{2}:\d{2}\b'),  # HH:MM:SS
            ],
            'PERCENT': [
                re.compile(r'\b\d+(?:\.\d+)?%\b'),  # Percentages
                re.compile(r'\b\d+(?:\.\d+)?\s+percent\b'),  # "percent" word
            ],
            'QUANTITY': [
                re.compile(r'\b\d+(?:,\d{3})*(?:\.\d+)?\s+(?:tons?|kilograms?|kg|pounds?|lbs|ounces?|oz|gallons?|liters?|meters?|feet?|inches?|miles?|kilometers?|acres?|hectares?|square\s+meters?|cubic\s+meters?)\b'),  # Quantities with units
            ],
        }

        # Common stop words and noise patterns to filter out
        self.stop_words = {
            'PERSON': {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a'},
            'ORG': {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a', 'this', 'that', 'these', 'those'},
            'GPE': {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a'},
            'EVENT': {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a'},
        }

        # Known entity aliases for disambiguation
        self.entity_aliases = {
            'PERSON': {
                'Joe Biden': ['Joseph Biden', 'President Biden', 'Joe R. Biden'],
                'Rishi Sunak': ['Prime Minister Sunak', 'Rishi Sunak MP'],
                'David Cameron': ['David William Donald Cameron', 'Prime Minister Cameron'],
                'Theresa May': ['Theresa Mary May', 'Prime Minister May'],
                'Boris Johnson': ['Alexander Boris de Pfeffel Johnson', 'Prime Minister Johnson'],
                'Keir Starmer': ['Sir Keir Starmer', 'Keir Rodney Starmer'],
            },
            'ORG': {
                'BBC': ['British Broadcasting Corporation', 'BBC News'],
                'Reuters': ['Thomson Reuters', 'Reuters News'],
                'Microsoft': ['Microsoft Corporation', 'Microsoft Corp'],
                'Apple': ['Apple Inc', 'Apple Inc.'],
            },
            'GPE': {
                'UK': ['United Kingdom', 'Britain', 'Great Britain'],
                'US': ['United States', 'USA', 'America'],
                'London': ['Greater London', 'City of London'],
            }
        }

        logger.info("🔍 Advanced entity extractor initialized with disambiguation capabilities")

    def extract_entities(self, text: str, context: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
        """
        Extract entities from text with advanced disambiguation

        Args:
            text: Article content text
            context: Optional context information (publisher, date, etc.)

        Returns:
            Dictionary of entity types to lists of entity dictionaries with confidence scores
        """
        entities = defaultdict(list)

        # Extract entities using all patterns
        for entity_type, patterns in self.entity_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                for match in matches:
                    if self._is_valid_entity(match, entity_type):
                        confidence = self._calculate_confidence(match, entity_type, text, context)
                        entities[entity_type].append({
                            'name': match,
                            'confidence': confidence,
                            'context': self._extract_context(text, match),
                            'aliases': self._find_aliases(match, entity_type)
                        })

        # Post-process and disambiguate entities
        entities = self._post_process_entities(entities)
        entities = self._disambiguate_entities(entities)

        return dict(entities)

    def _is_valid_entity(self, entity: str, entity_type: str) -> bool:
        """Validate if an extracted string is a valid entity"""
        if len(entity) < 3:
            return False

        # Check for stop words
        words = entity.lower().split()
        if any(word in self.stop_words.get(entity_type, set()) for word in words):
            return False

        # Check for common false positives
        false_positives = {
            'PERSON': ['Prime Minister', 'President', 'Government', 'Parliament', 'Cabinet', 'Ministry', 'Department', 'Committee', 'Council', 'Board', 'Commission', 'Agency', 'Service', 'Office', 'House', 'Party', 'Union', 'Association', 'Society', 'Institute', 'Center', 'Centre', 'Foundation', 'Trust', 'Authority', 'Corporation', 'Company', 'Group', 'Media', 'News', 'Press', 'Journal', 'Times', 'Post', 'Daily', 'Weekly', 'Monthly', 'Yearly'],
            'ORG': ['Prime Minister', 'President', 'Government', 'Parliament', 'Cabinet', 'Ministry', 'Department', 'Committee', 'Council', 'Board', 'Commission', 'Agency', 'Service', 'Office', 'House', 'Party', 'Union', 'Association', 'Society', 'Institute', 'Center', 'Centre', 'Foundation', 'Trust', 'Authority'],
            'GPE': ['Prime Minister', 'President', 'Government', 'Parliament', 'Cabinet', 'Ministry', 'Department', 'Committee', 'Council', 'Board', 'Commission', 'Agency', 'Service', 'Office', 'House', 'Party', 'Union', 'Association', 'Society', 'Institute', 'Center', 'Centre', 'Foundation', 'Trust', 'Authority', 'Corporation', 'Company', 'Group', 'Media', 'News', 'Press', 'Journal', 'Times', 'Post', 'Daily', 'Weekly', 'Monthly', 'Yearly'],
            'EVENT': ['Prime Minister', 'President', 'Government', 'Parliament', 'Cabinet', 'Ministry', 'Department', 'Committee', 'Council', 'Board', 'Commission', 'Agency', 'Service', 'Office', 'House', 'Party', 'Union', 'Association', 'Society', 'Institute', 'Center', 'Centre', 'Foundation', 'Trust', 'Authority', 'Corporation', 'Company', 'Group', 'Media', 'News', 'Press', 'Journal', 'Times', 'Post', 'Daily', 'Weekly', 'Monthly', 'Yearly'],
        }

        if entity in false_positives.get(entity_type, []):
            return False

        # For PERSON entities, ensure they look like actual names
        if entity_type == 'PERSON':
            # Must have at least one capital letter after the first character
            if not re.search(r'[A-Z][a-z]+.*[A-Z]', entity):
                return False
            # Must not be all caps or have numbers
            if entity.isupper() or re.search(r'\d', entity):
                return False

        # For ORG entities, ensure they have organization-like characteristics
        if entity_type == 'ORG':
            # Must have at least one capital letter
            if not re.search(r'[A-Z]', entity):
                return False

        # For GPE entities, ensure they look like place names
        if entity_type == 'GPE':
            # Must have at least one capital letter
            if not re.search(r'[A-Z]', entity):
                return False
            # Filter out obvious non-places
            non_places = ['The', 'And', 'Or', 'But', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By', 'An', 'A']
            if entity in non_places:
                return False

        return True

    def _calculate_confidence(self, entity: str, entity_type: str, text: str,
                            context: dict[str, Any] | None = None) -> float:
        """Calculate confidence score for extracted entity with enhanced analysis"""
        confidence = 0.5  # Base confidence

        # Length factor (longer entities are generally more specific)
        confidence += min(len(entity) / 50, 0.2)

        # Capitalization factor (proper nouns are more likely entities)
        if entity.istitle():
            confidence += 0.15

        # Context factor (mentions in title or first paragraph)
        if context and 'title' in context:
            if entity in context['title']:
                confidence += 0.25

        # Frequency factor (repeated mentions increase confidence)
        entity_count = text.count(entity)
        confidence += min(entity_count / 10, 0.15)

        # Pattern specificity factor
        if re.search(r'\b(Inc|Corp|LLC|Ltd|Company|Corporation|University|College|Institute|Foundation|Government|Ministry|Department|Agency|Council|Commission|Bank|Media|News|Press|International|Global|National|Federal|State|City|County|Association|Organization|Institute|Center|Centre|Services|Systems|Technologies|AG|GmbH|BV|NV|SAS|SARL|SL|SA|PLC|Limited|Incorporated)\b', entity):
            confidence += 0.15

        # Entity type specific factors
        if entity_type == 'PERSON':
            # Check for title + name pattern
            if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|President|Prime\s+Minister|CEO|Chairman|Director|Senator|Governor|Mayor|Ambassador)\.?\s+[A-Z][a-z]+\b', entity):
                confidence += 0.1
            # Check for multi-part names
            if len(entity.split()) >= 2:
                confidence += 0.05

        elif entity_type == 'ORG':
            # Known reliable organizations
            reliable_orgs = {'BBC', 'Reuters', 'CNN', 'AP', 'NATO', 'UN', 'EU', 'WHO', 'WTO', 'IMF', 'World Bank', 'FBI', 'CIA', 'NASA', 'FDA'}
            if any(org in entity.upper() for org in reliable_orgs):
                confidence += 0.2

        elif entity_type == 'GPE':
            # Major cities/countries get higher confidence
            major_places = {'London', 'Paris', 'Berlin', 'Tokyo', 'New York', 'Washington', 'Beijing', 'Moscow', 'United Kingdom', 'United States', 'Germany', 'France', 'China', 'Japan', 'Russia', 'Canada', 'Australia'}
            if any(place in entity for place in major_places):
                confidence += 0.1

        elif entity_type == 'MONEY':
            # Financial amounts in news are usually reliable
            confidence += 0.1

        elif entity_type == 'DATE':
            # Dates in news articles are usually accurate
            confidence += 0.1

        # Contextual validation
        confidence += self._calculate_contextual_confidence(entity, entity_type, text)

        return min(confidence, 1.0)

    def _calculate_contextual_confidence(self, entity: str, entity_type: str, text: str) -> float:
        """Calculate contextual confidence based on surrounding words"""
        confidence = 0.0

        # Get context around entity mentions
        text_lower = text.lower()

        # Look for contextual indicators
        context_indicators = {
            'PERSON': ['said', 'stated', 'announced', 'commented', 'told', 'asked', 'responded', 'explained', 'noted', 'added', 'continued', 'concluded', 'emphasized', 'stressed', 'pointed out', 'mentioned', 'revealed', 'disclosed', 'confirmed', 'denied', 'admitted', 'claimed', 'argued', 'suggested', 'proposed', 'recommended', 'urged', 'called for', 'demanded', 'requested', 'appealed', 'pleaded', 'begged', 'implored', 'insisted', 'maintained', 'asserted', 'declared', 'proclaimed', 'affirmed', 'vowed', 'pledged', 'promised', 'guaranteed', 'assured', 'reassured', 'convinced', 'persuaded', 'influenced', 'swayed', 'moved', 'touched', 'inspired', 'motivated', 'encouraged', 'discouraged', 'dissuaded', 'deterred', 'prevented', 'stopped', 'halted', 'blocked', 'obstructed', 'impeded', 'hindered', 'delayed', 'postponed', 'cancelled', 'abandoned', 'suspended', 'terminated', 'ended', 'finished', 'completed', 'concluded', 'finalized', 'settled', 'resolved', 'solved', 'fixed', 'repaired', 'restored', 'renewed', 'revived', 'rejuvenated', 'refreshed', 'recharged', 'reenergized', 'reinforced', 'strengthened', 'weakened', 'damaged', 'destroyed', 'ruined', 'wrecked', 'devastated', 'annihilated', 'obliterated', 'eliminated', 'erased', 'wiped out', 'extinguished', 'extinguished', 'quenched', 'squelched', 'suppressed', 'repressed', 'oppressed', 'persecuted', 'harassed', 'bullied', 'intimidated', 'threatened', 'menaced', 'endangered', 'jeopardized', 'risked', 'gambled', 'wagered', 'bet', 'speculated', 'hypothesized', 'theorized', 'postulated', 'posited', 'assumed', 'presumed', 'supposed', 'imagined', 'envisioned', 'foreseen', 'predicted', 'forecasted', 'anticipated', 'expected', 'hoped', 'wished', 'desired', 'wanted', 'needed', 'required', 'demanded', 'requested', 'asked for', 'sought', 'pursued', 'chased', 'hunted', 'searched for', 'looked for', 'sought out', 'tracked down', 'traced', 'followed', 'pursued', 'chased', 'hunted', 'searched for', 'looked for', 'sought out', 'tracked down', 'traced', 'followed'],
            'ORG': ['announced', 'reported', 'published', 'released', 'issued', 'stated', 'confirmed', 'denied', 'admitted', 'claimed', 'revealed', 'disclosed', 'exposed', 'uncovered', 'discovered', 'found', 'located', 'identified', 'recognized', 'acknowledged', 'accepted', 'rejected', 'declined', 'refused', 'turned down', 'dismissed', 'ignored', 'overlooked', 'neglected', 'forgot', 'omitted', 'excluded', 'eliminated', 'removed', 'deleted', 'erased', 'wiped out', 'cleared', 'purged', 'expunged', 'obliterated', 'annihilated', 'destroyed', 'ruined', 'wrecked', 'devastated', 'demolished', 'razed', 'leveled', 'flattened', 'pulled down', 'torn down', 'knocked down', 'brought down', 'toppled', 'overthrown', 'deposed', 'ousted', 'ejected', 'expelled', 'banished', 'exiled', 'deported', 'evicted', 'displaced', 'relocated', 'moved', 'transferred', 'shifted', 'switched', 'changed', 'altered', 'modified', 'adjusted', 'adapted', 'customized', 'personalized', 'tailored', 'fitted', 'suited', 'matched', 'corresponded', 'agreed', 'concurred', 'consented', 'approved', 'authorized', 'permitted', 'allowed', 'enabled', 'facilitated', 'promoted', 'encouraged', 'supported', 'backed', 'endorsed', 'championed', 'advocated', 'defended', 'protected', 'shielded', 'guarded', 'safeguarded', 'preserved', 'maintained', 'kept', 'retained', 'held', 'possessed', 'owned', 'controlled', 'managed', 'directed', 'led', 'guided', 'steered', 'piloted', 'navigated', 'commanded', 'ordered', 'instructed', 'directed', 'told', 'advised', 'counseled', 'consulted', 'recommended', 'suggested', 'proposed', 'offered', 'presented', 'submitted', 'filed', 'lodged', 'registered', 'recorded', 'documented', 'noted', 'marked', 'indicated', 'showed', 'displayed', 'exhibited', 'demonstrated', 'proved', 'verified', 'confirmed', 'validated', 'authenticated', 'certified', 'endorsed', 'approved', 'sanctioned', 'ratified', 'confirmed', 'validated', 'authenticated', 'certified', 'endorsed', 'approved', 'sanctioned', 'ratified'],
            'GPE': ['located', 'based', 'situated', 'positioned', 'placed', 'established', 'founded', 'created', 'built', 'constructed', 'developed', 'expanded', 'grown', 'increased', 'risen', 'climbed', 'soared', 'surged', 'boomed', 'exploded', 'skyrocketed', 'multiplied', 'doubled', 'tripled', 'quadrupled', 'quintupled', 'increased', 'rose', 'grew', 'expanded', 'swelled', 'ballooned', 'bloated', 'enlarged', 'extended', 'stretched', 'widened', 'broadened', 'amplified', 'magnified', 'intensified', 'heightened', 'elevated', 'raised', 'lifted', 'boosted', 'enhanced', 'improved', 'better', 'superior', 'excellent', 'outstanding', 'exceptional', 'remarkable', 'extraordinary', 'amazing', 'astonishing', 'astounding', 'incredible', 'unbelievable', 'miraculous', 'phenomenal', 'spectacular', 'stunning', 'breathtaking', 'awesome', 'fabulous', 'fantastic', 'great', 'wonderful', 'marvelous', 'superb', 'splendid', 'magnificent', 'glorious', 'brilliant', 'dazzling', 'radiant', 'shining', 'gleaming', 'sparkling', 'twinkling', 'glittering', 'lustrous', 'luminous', 'bright', 'vivid', 'intense', 'strong', 'powerful', 'mighty', 'potent', 'forceful', 'vigorous', 'energetic', 'dynamic', 'active', 'lively', 'animated', 'spirited', 'enthusiastic', 'eager', 'keen', 'avid', 'ardent', 'fervent', 'passionate', 'intense', 'fierce', 'ferocious', 'savage', 'wild', 'untamed', 'uncontrolled', 'unrestrained', 'unchecked', 'unbridled', 'rampant', 'widespread', 'prevalent', 'common', 'frequent', 'regular', 'normal', 'usual', 'typical', 'standard', 'ordinary', 'average', 'median', 'mean', 'middle', 'central', 'core', 'heart', 'center', 'hub', 'focus', 'nucleus', 'kernel', 'essence', 'core', 'heart', 'soul', 'spirit', 'lifeblood', 'vitality', 'energy', 'vigor', 'strength', 'power', 'might', 'force', 'potency', 'efficacy', 'effectiveness', 'efficiency', 'productivity', 'performance', 'achievement', 'accomplishment', 'success', 'triumph', 'victory', 'win', 'gain', 'profit', 'benefit', 'advantage', 'edge', 'upper hand', 'lead', 'head start', 'foothold', 'beachhead', 'stronghold', 'fortress', 'bastion', 'citadel', 'stronghold', 'fortress', 'bastion', 'citadel'],
            'EVENT': ['occurred', 'happened', 'took place', 'transpired', 'came about', 'came to pass', 'befell', 'betided', 'chanced', 'fell out', 'turned out', 'worked out', 'ended up', 'resulted', 'led to', 'caused', 'produced', 'generated', 'created', 'made', 'formed', 'shaped', 'molded', 'fashioned', 'crafted', 'built', 'constructed', 'erected', 'raised', 'built up', 'put up', 'set up', 'established', 'founded', 'started', 'began', 'commenced', 'initiated', 'launched', 'inaugurated', 'opened', 'unveiled', 'revealed', 'disclosed', 'announced', 'declared', 'proclaimed', 'stated', 'said', 'told', 'reported', 'mentioned', 'noted', 'observed', 'remarked', 'commented', 'added', 'continued', 'went on', 'proceeded', 'advanced', 'progressed', 'developed', 'evolved', 'changed', 'transformed', 'converted', 'turned', 'became', 'grew into', 'developed into', 'evolved into', 'turned into', 'changed into', 'transformed into', 'converted into', 'metamorphosed into', 'transmuted into', 'transfigured into', 'reincarnated into', 'reborn into', 'renewed into', 'revived into', 'resurrected into', 'restored into', 'rehabilitated into', 'reconstructed into', 'rebuilt into', 'remodeled into', 'renovated into', 'refurbished into', 'repaired into', 'fixed into', 'mended into', 'healed into', 'cured into', 'treated into', 'remedied into', 'rectified into', 'corrected into', 'amended into', 'revised into', 'modified into', 'adjusted into', 'adapted into', 'customized into', 'personalized into', 'tailored into', 'fitted into', 'suited into', 'matched into', 'corresponded into', 'agreed into', 'concurred into', 'consented into', 'approved into', 'authorized into', 'permitted into', 'allowed into', 'enabled into', 'facilitated into', 'promoted into', 'encouraged into', 'supported into', 'backed into', 'endorsed into', 'championed into', 'advocated into', 'defended into', 'protected into', 'shielded into', 'guarded into', 'safeguarded into', 'preserved into', 'maintained into', 'kept into', 'retained into', 'held into', 'possessed into', 'owned into', 'controlled into', 'managed into', 'directed into', 'led into', 'guided into', 'steered into', 'piloted into', 'navigated into', 'commanded into', 'ordered into', 'instructed into', 'directed into', 'told into', 'advised into', 'counseled into', 'consulted into', 'recommended into', 'suggested into', 'proposed into', 'offered into', 'presented into', 'submitted into', 'filed into', 'lodged into', 'registered into', 'recorded into', 'documented into', 'noted into', 'marked into', 'indicated into', 'showed into', 'displayed into', 'exhibited into', 'demonstrated into', 'proved into', 'verified into', 'confirmed into', 'validated into', 'authenticated into', 'certified into', 'endorsed into', 'approved into', 'sanctioned into', 'ratified into', 'confirmed into', 'validated into', 'authenticated into', 'certified into', 'endorsed into', 'approved into', 'sanctioned into', 'ratified into'],
        }

        indicators = context_indicators.get(entity_type, [])
        for indicator in indicators:
            if indicator in text_lower:
                confidence += 0.02  # Small boost for each contextual indicator

        return min(confidence, 0.2)  # Cap contextual confidence at 0.2

    def _extract_context(self, text: str, entity: str, window_size: int = 50) -> str:
        """Extract context around entity mention"""
        try:
            idx = text.find(entity)
            if idx == -1:
                return ""

            start = max(0, idx - window_size)
            end = min(len(text), idx + len(entity) + window_size)
            context = text[start:end]

            # Clean up context
            context = re.sub(r'\s+', ' ', context).strip()
            return context
        except (ValueError, TypeError, AttributeError):
            return ""

    def _find_aliases(self, entity: str, entity_type: str) -> list[str]:
        """Find known aliases for an entity"""
        aliases = []

        # Check known aliases
        for canonical, alias_list in self.entity_aliases.get(entity_type, {}).items():
            if entity == canonical or entity in alias_list:
                aliases.extend([canonical] + alias_list)
                break

        # Generate potential aliases based on patterns
        if entity_type == 'PERSON':
            # Handle titles
            if 'Prime Minister' in entity:
                name = entity.replace('Prime Minister', '').strip()
                aliases.extend([name, f"PM {name}"])
            elif 'President' in entity:
                name = entity.replace('President', '').strip()
                aliases.extend([name, f"President {name}"])

        return list(set(aliases))

    def _post_process_entities(self, entities: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """Post-process extracted entities for better quality"""
        processed = defaultdict(list)

        for entity_type, entity_list in entities.items():
            # Remove duplicates based on name
            seen_names = set()
            unique_entities = []

            for entity in entity_list:
                name = entity['name']
                if name not in seen_names:
                    seen_names.add(name)
                    unique_entities.append(entity)

            # Sort by confidence
            unique_entities.sort(key=lambda x: x['confidence'], reverse=True)

            # Filter low confidence entities
            filtered_entities = [e for e in unique_entities if e['confidence'] > 0.3]

            processed[entity_type] = filtered_entities

        return dict(processed)

    def _disambiguate_entities(self, entities: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """Disambiguate similar entities using clustering"""
        disambiguated = defaultdict(list)

        for entity_type, entity_list in entities.items():
            if not entity_list:
                continue

            # Group similar entities
            clusters = self._cluster_similar_entities(entity_list)

            # Select best representative for each cluster
            for cluster in clusters:
                if cluster:
                    # Sort by confidence and select the highest
                    cluster.sort(key=lambda x: x['confidence'], reverse=True)
                    best_entity = cluster[0].copy()

                    # Merge aliases from all cluster members
                    all_aliases = set()
                    for entity in cluster:
                        all_aliases.update(entity.get('aliases', []))

                    best_entity['aliases'] = list(all_aliases)
                    best_entity['cluster_size'] = len(cluster)

                    disambiguated[entity_type].append(best_entity)

        return dict(disambiguated)

    def _cluster_similar_entities(self, entities: list[dict[str, Any]],
                                similarity_threshold: float = 0.8) -> list[list[dict[str, Any]]]:
        """Cluster similar entities based on name similarity"""
        clusters = []
        unclustered = entities.copy()

        while unclustered:
            entity = unclustered.pop(0)
            cluster = [entity]

            # Find similar entities
            similar_indices = []
            for i, other_entity in enumerate(unclustered):
                similarity = self._calculate_similarity(entity['name'], other_entity['name'])
                if similarity >= similarity_threshold:
                    cluster.append(other_entity)
                    similar_indices.append(i)

            # Remove similar entities from unclustered list
            for i in reversed(similar_indices):
                unclustered.pop(i)

            clusters.append(cluster)

        return clusters

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings"""
        # Use sequence matcher for basic similarity
        similarity = SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

        # Boost similarity for substring matches
        if str1.lower() in str2.lower() or str2.lower() in str1.lower():
            similarity = max(similarity, 0.9)

        # Boost similarity for shared words
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        word_overlap = len(words1.intersection(words2)) / max(len(words1), len(words2)) if words1 and words2 else 0

        return max(similarity, word_overlap)

class EntityExtractor(AdvancedEntityExtractor):
    """
    Backward-compatible entity extractor that extends AdvancedEntityExtractor

    This maintains the original interface while providing advanced capabilities
    """

    def extract_entities(self, text: str) -> dict[str, list[str]]:
        """
        Extract entities from text content (backward-compatible interface)

        Args:
            text: Article content text

        Returns:
            Dictionary of entity types to lists of extracted entity names
        """
        # Use advanced extraction
        advanced_entities = super().extract_entities(text)

        # Convert to simple format for backward compatibility
        simple_entities = {}
        for entity_type, entity_list in advanced_entities.items():
            simple_entities[entity_type] = [entity['name'] for entity in entity_list]

        return simple_entities

class KnowledgeGraphNode:
    """
    Represents a node in the knowledge graph

    Nodes can represent entities, articles, or temporal events
    """

    def __init__(self, node_id: str, node_type: str, properties: dict[str, Any]):
        self.node_id = node_id
        self.node_type = node_type
        self.properties = properties
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        """Convert node to dictionary representation"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'KnowledgeGraphNode':
        """Create node from dictionary representation"""
        node = cls(data["node_id"], data["node_type"], data["properties"])
        node.created_at = data.get("created_at", node.created_at)
        node.updated_at = data.get("updated_at", node.updated_at)
        return node

class KnowledgeGraphEdge:
    """
    Represents an edge/relationship in the knowledge graph with strength analysis

    Edges connect nodes with typed relationships and temporal information
    Enhanced with relationship strength and confidence scoring
    """

    def __init__(self, source_id: str, target_id: str, edge_type: str,
                 properties: dict[str, Any] = None):
        self.source_id = source_id
        self.target_id = target_id
        self.edge_type = edge_type
        self.properties = properties or {}
        self.created_at = datetime.now().isoformat()

        # Relationship strength analysis
        self.strength = self._calculate_strength()
        self.confidence = self._calculate_confidence()

    def _calculate_strength(self) -> float:
        """Calculate relationship strength based on various factors"""
        strength = 0.5  # Base strength

        # Frequency factor (how often entities co-occur)
        co_occurrence_count = self.properties.get('co_occurrence_count', 1)
        strength += min(co_occurrence_count / 10, 0.3)

        # Proximity factor (how close entities appear in text)
        proximity_score = self.properties.get('proximity_score', 0.5)
        strength += proximity_score * 0.2

        # Context factor (semantic relationship indicators)
        context_indicators = self.properties.get('context_indicators', [])
        strength += len(context_indicators) * 0.1

        # Temporal factor (consistent relationships over time)
        temporal_consistency = self.properties.get('temporal_consistency', 1)
        strength += temporal_consistency * 0.1

        return min(strength, 1.0)

    def _calculate_confidence(self) -> float:
        """Calculate confidence score for the relationship"""
        confidence = 0.5  # Base confidence

        # Source reliability factor
        source_reliability = self.properties.get('source_reliability', 0.8)
        confidence += source_reliability * 0.2

        # Entity confidence factor
        entity_confidence = self.properties.get('entity_confidence', 0.8)
        confidence += entity_confidence * 0.2

        # Pattern matching factor
        pattern_matches = self.properties.get('pattern_matches', 1)
        confidence += min(pattern_matches / 5, 0.2)

        # Cross-validation factor
        cross_validation = self.properties.get('cross_validation', 0)
        confidence += cross_validation * 0.1

        return min(confidence, 1.0)

    def to_dict(self) -> dict[str, Any]:
        """Convert edge to dictionary representation"""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "properties": self.properties,
            "strength": self.strength,
            "confidence": self.confidence,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'KnowledgeGraphEdge':
        """Create edge from dictionary representation"""
        edge = cls(data["source_id"], data["target_id"], data["edge_type"], data["properties"])
        edge.created_at = data.get("created_at", edge.created_at)
        edge.strength = data.get("strength", edge.strength)
        edge.confidence = data.get("confidence", edge.confidence)
        return edge

class EntityClustering:
    """Advanced entity clustering for grouping similar entities"""

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self.clusters = {}
        self.entity_aliases = {}

    def cluster_entities(self, entities: list[str]) -> dict[str, list[str]]:
        """
        Cluster similar entities based on string similarity and context

        Args:
            entities: List of entity names to cluster

        Returns:
            Dictionary mapping cluster representatives to list of similar entities
        """
        clusters = {}

        for entity in entities:
            # Find best matching cluster
            best_match = None
            best_score = 0

            for representative in clusters.keys():
                similarity = self._calculate_entity_similarity(entity, representative)
                if similarity > best_score and similarity >= self.similarity_threshold:
                    best_score = similarity
                    best_match = representative

            if best_match:
                clusters[best_match].append(entity)
                self.entity_aliases[entity] = best_match
            else:
                clusters[entity] = [entity]

        self.clusters = clusters
        return clusters

    def _calculate_entity_similarity(self, entity1: str, entity2: str) -> float:
        """Calculate similarity between two entities using multiple methods"""
        # Normalize entities for comparison
        e1_norm = self._normalize_entity(entity1)
        e2_norm = self._normalize_entity(entity2)

        # Exact match after normalization
        if e1_norm == e2_norm:
            return 1.0

        # SequenceMatcher similarity
        seq_similarity = SequenceMatcher(None, e1_norm, e2_norm).ratio()

        # Jaccard similarity for word sets
        words1 = set(e1_norm.lower().split())
        words2 = set(e2_norm.lower().split())
        jaccard = len(words1.intersection(words2)) / len(words1.union(words2)) if words1.union(words2) else 0

        # Weighted combination
        similarity = (seq_similarity * 0.6) + (jaccard * 0.4)

        # Boost similarity for common abbreviations/initialisms
        if self._is_abbreviation_match(entity1, entity2):
            similarity = min(1.0, similarity + 0.2)

        return similarity

    def _normalize_entity(self, entity: str) -> str:
        """Normalize entity name for comparison"""
        # Remove common titles and suffixes
        normalized = entity.strip()

        # Handle common abbreviations
        abbr_patterns = [
            (r'\bMr\.?\s+', ''),
            (r'\bMrs\.?\s+', ''),
            (r'\bDr\.?\s+', ''),
            (r'\bProf\.?\s+', ''),
            (r'\bPresident\s+', ''),
            (r'\bPrime\s+Minister\s+', ''),
            (r'\bMinister\s+', ''),
            (r'\bDirector\s+', ''),
            (r'\bCEO\s+', ''),
            (r'\bInc\.?\s*$', ''),
            (r'\bLtd\.?\s*$', ''),
            (r'\bLLC\.?\s*$', ''),
            (r'\bCorp\.?\s*$', ''),
            (r'\bCorporation\s*$', ''),
            (r'\bCompany\s*$', ''),
            (r'\bCo\.?\s*$', ''),
        ]

        for pattern, replacement in abbr_patterns:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        return normalized.strip()

    def _is_abbreviation_match(self, entity1: str, entity2: str) -> bool:
        """Check if entities match as abbreviation/full name"""
        # Simple abbreviation detection
        words1 = entity1.upper().split()
        words2 = entity2.upper().split()

        # Check if one is abbreviation of the other
        if len(words1) == 1 and len(words2) > 1:
            # entity1 might be abbreviation of entity2
            abbr = ''.join(w[0] for w in words2 if w)
            return words1[0] == abbr
        elif len(words2) == 1 and len(words1) > 1:
            # entity2 might be abbreviation of entity1
            abbr = ''.join(w[0] for w in words1 if w)
            return words2[0] == abbr

        return False

    def merge_clusters(self, graph: nx.MultiDiGraph) -> dict[str, str]:
        """
        Merge entity clusters in the knowledge graph

        Args:
            graph: NetworkX graph to update

        Returns:
            Mapping of old entity IDs to new representative IDs
        """
        merged_entities = {}

        for representative, cluster_entities in self.clusters.items():
            if len(cluster_entities) > 1:
                # Find all nodes for these entities
                entity_nodes = []
                for entity in cluster_entities:
                    for node_id, node_data in graph.nodes(data=True):
                        if (node_data.get("node_type") == "entity" and
                            node_data["properties"].get("name") == entity):
                            entity_nodes.append(node_id)

                if len(entity_nodes) > 1:
                    # Merge nodes - keep the first one as representative
                    representative_node = entity_nodes[0]
                    nodes_to_merge = entity_nodes[1:]

                    # Update properties of representative node
                    rep_props = graph.nodes[representative_node]["properties"]
                    rep_props["aliases"] = cluster_entities
                    rep_props["cluster_size"] = len(cluster_entities)
                    rep_props["merged_entities"] = nodes_to_merge

                    # Redirect edges from merged nodes to representative
                    for node_to_merge in nodes_to_merge:
                        # Get all edges from/to this node
                        incoming_edges = list(graph.in_edges(node_to_merge, data=True, keys=True))
                        outgoing_edges = list(graph.out_edges(node_to_merge, data=True, keys=True))

                        # Redirect incoming edges
                        for source, _, key, data in incoming_edges:
                            if not graph.has_edge(source, representative_node, key):
                                graph.add_edge(source, representative_node, key, **data)

                        # Redirect outgoing edges
                        for _, target, key, data in outgoing_edges:
                            if not graph.has_edge(representative_node, target, key):
                                graph.add_edge(representative_node, target, key, **data)

                        # Remove merged node
                        graph.remove_node(node_to_merge)
                        merged_entities[node_to_merge] = representative_node

        return merged_entities

    def get_cluster_confidence(self, cluster: list[str]) -> float:
        """Calculate confidence score for a cluster"""
        if len(cluster) <= 1:
            return 1.0

        # Calculate average pairwise similarity
        similarities = []
        for i, entity1 in enumerate(cluster):
            for entity2 in cluster[i+1:]:
                sim = self._calculate_entity_similarity(entity1, entity2)
                similarities.append(sim)

        if not similarities:
            return 0.0

        avg_similarity = sum(similarities) / len(similarities)

        # Boost confidence for larger clusters with high similarity
        size_bonus = min(len(cluster) / 10, 0.2)  # Max 0.2 bonus for 10+ entities

        confidence = avg_similarity + size_bonus

        return min(confidence, 1.0)

class TemporalKnowledgeGraph:
    """
    Temporal knowledge graph that tracks relationships over time

    Supports time-aware queries and relationship evolution tracking
    """

    def __init__(self, storage_path: str = "./kg_storage"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

        # In-memory graph for fast operations
        self.graph = nx.MultiDiGraph()

        # Entity extractor
        self.entity_extractor = EntityExtractor()

        # Entity clustering
        self.entity_clustering = EntityClustering()

        # Node and edge storage
        self.nodes_file = self.storage_path / "nodes.jsonl"
        self.edges_file = self.storage_path / "edges.jsonl"

        # Load existing graph if available
        self._load_graph()

        logger.info("🕐 Temporal Knowledge Graph initialized")

    def _load_graph(self):
        """Load existing graph from storage"""
        try:
            # Load nodes
            if self.nodes_file.exists():
                with open(self.nodes_file, encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            node_data = json.loads(line)
                            node = KnowledgeGraphNode.from_dict(node_data)
                            self.graph.add_node(node.node_id, **node.to_dict())

            # Load edges
            if self.edges_file.exists():
                with open(self.edges_file, encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            edge_data = json.loads(line)
                            edge = KnowledgeGraphEdge.from_dict(edge_data)
                            self.graph.add_edge(edge.source_id, edge.target_id,
                                              key=edge.edge_type, **edge.to_dict())

            logger.info(f"📚 Loaded graph with {len(self.graph.nodes)} nodes and {len(self.graph.edges)} edges")

        except Exception as e:
            logger.error(f"Failed to load graph: {e}")

    def _save_graph(self):
        """Save graph to storage"""
        try:
            # Save nodes
            with open(self.nodes_file, 'w', encoding='utf-8') as f:
                for node_id in self.graph.nodes():
                    node_data = self.graph.nodes[node_id]
                    f.write(json.dumps(node_data, ensure_ascii=False) + '\n')

            # Save edges
            with open(self.edges_file, 'w', encoding='utf-8') as f:
                for source, target, key, edge_data in self.graph.edges(keys=True, data=True):
                    edge_dict = {
                        "source_id": source,
                        "target_id": target,
                        "edge_type": key,
                        **edge_data
                    }
                    f.write(json.dumps(edge_dict, ensure_ascii=False) + '\n')

            logger.debug("💾 Graph saved to storage")

        except Exception as e:
            logger.error(f"Failed to save graph: {e}")

    def add_article_node(self, article_data: dict[str, Any]) -> str:
        """
        Add an article as a node in the knowledge graph

        Args:
            article_data: Article metadata and content

        Returns:
            Node ID of the created article node
        """
        # Generate node ID
        node_id = f"article_{article_data.get('url_hash', hashlib.sha256(article_data['url'].encode()).hexdigest())}"

        # Extract entities from content
        entities = {}
        if 'content' in article_data:
            entities = self.entity_extractor.extract_entities(article_data['content'])

        # Create node properties
        properties = {
            "url": article_data["url"],
            "title": article_data.get("title", ""),
            "domain": article_data.get("domain", ""),
            "published_date": article_data.get("timestamp", ""),
            "entities": entities,
            "news_score": article_data.get("news_score", 0.0),
            "extraction_method": article_data.get("extraction_method", ""),
            "canonical_url": article_data.get("canonical", ""),
            "publisher": article_data.get("publisher_meta", {}).get("publisher", "")
        }

        # Create and add node
        node = KnowledgeGraphNode(node_id, "article", properties)
        self.graph.add_node(node_id, **node.to_dict())

        logger.info(f"📄 Added article node: {article_data.get('title', 'Unknown')[:50]}...")
        return node_id

    def add_entity_nodes(self, entities: dict[str, list[str]]) -> dict[str, str]:
        """
        Add entity nodes to the knowledge graph

        Args:
            entities: Dictionary of entity types to entity names

        Returns:
            Mapping of entity names to node IDs
        """
        entity_nodes = {}

        for entity_type, entity_list in entities.items():
            for entity_name in entity_list:
                # Generate node ID
                node_id = f"entity_{entity_type.lower()}_{hashlib.sha256(entity_name.encode()).hexdigest()[:8]}"

                # Create node properties
                properties = {
                    "name": entity_name,
                    "entity_type": entity_type,
                    "mention_count": 1,  # Will be updated if entity already exists
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat()
                }

                # Check if entity node already exists
                if node_id in self.graph.nodes:
                    # Update existing node
                    existing_props = self.graph.nodes[node_id]["properties"]
                    existing_props["mention_count"] += 1
                    existing_props["last_seen"] = datetime.now().isoformat()
                    self.graph.nodes[node_id]["updated_at"] = datetime.now().isoformat()
                else:
                    # Create new node
                    node = KnowledgeGraphNode(node_id, "entity", properties)
                    self.graph.add_node(node_id, **node.to_dict())

                entity_nodes[entity_name] = node_id

        logger.info(f"🏷️ Added {len(entity_nodes)} entity nodes")
        return entity_nodes

    def add_relationships(self, article_node_id: str, entity_nodes: dict[str, str],
                         article_data: dict[str, Any]):
        """
        Add relationships between article and entities with strength analysis

        Args:
            article_node_id: ID of the article node
            entity_nodes: Mapping of entity names to node IDs
            article_data: Original article data for context
        """
        published_date = article_data.get("timestamp", datetime.now().isoformat())
        article_text = article_data.get("content", "")

        # Analyze entity co-occurrences and relationships
        entity_relationships = self._analyze_entity_relationships(
            list(entity_nodes.keys()), article_text
        )

        for entity_name, entity_node_id in entity_nodes.items():
            # Create "mentions" relationship with strength analysis
            relationship_properties = {
                "mentioned_at": published_date,
                "context": article_data.get("title", ""),
                "domain": article_data.get("domain", ""),
                "entity_name": entity_name,
                "entity_type": self.graph.nodes[entity_node_id]["properties"].get("entity_type", "unknown"),
                "co_occurrence_count": entity_relationships.get(entity_name, {}).get("frequency", 1),
                "proximity_score": entity_relationships.get(entity_name, {}).get("proximity", 0.5),
                "context_indicators": entity_relationships.get(entity_name, {}).get("indicators", []),
                "temporal_consistency": self._calculate_temporal_consistency(entity_name, published_date),
                "source_reliability": self._calculate_source_reliability(article_data),
                "entity_confidence": self.graph.nodes[entity_node_id]["properties"].get("confidence", 0.8),
                "pattern_matches": len(entity_relationships.get(entity_name, {}).get("patterns", [])),
                "cross_validation": self._calculate_cross_validation(entity_name, article_data)
            }

            edge = KnowledgeGraphEdge(
                article_node_id,
                entity_node_id,
                "mentions",
                relationship_properties
            )

            self.graph.add_edge(article_node_id, entity_node_id,
                              key="mentions", **edge.to_dict())

            # Create temporal relationship with strength analysis
            temporal_properties = {
                "timestamp": published_date,
                "temporal_context": "article_publication",
                "relationship_strength": edge.strength,
                "confidence_score": edge.confidence,
                "time_window": self._calculate_time_window(published_date)
            }

            temporal_edge = KnowledgeGraphEdge(
                entity_node_id,
                article_node_id,
                "mentioned_at_time",
                temporal_properties
            )

            self.graph.add_edge(entity_node_id, article_node_id,
                              key="mentioned_at_time", **temporal_edge.to_dict())

        logger.info(f"🔗 Added relationships for article: {article_node_id} with strength analysis")

    def _analyze_entity_relationships(self, entity_names: list[str], text: str) -> dict[str, dict[str, Any]]:
        """Analyze relationships between entities in the text"""
        relationships = {}

        for entity_name in entity_names:
            # Find all occurrences of the entity
            occurrences = []
            start = 0
            while True:
                idx = text.find(entity_name, start)
                if idx == -1:
                    break
                occurrences.append(idx)
                start = idx + 1

            # Calculate frequency
            frequency = len(occurrences)

            # Calculate proximity to other entities
            proximity_scores = []
            for other_entity in entity_names:
                if other_entity != entity_name:
                    min_distance = float('inf')
                    for idx1 in occurrences:
                        for idx2 in [text.find(other_entity, 0)]:
                            if idx2 != -1:
                                distance = abs(idx1 - idx2)
                                min_distance = min(min_distance, distance)

                    if min_distance < float('inf'):
                        # Convert distance to proximity score (closer = higher score)
                        proximity_score = max(0, 1 - (min_distance / 1000))
                        proximity_scores.append(proximity_score)

            avg_proximity = sum(proximity_scores) / len(proximity_scores) if proximity_scores else 0.5

            # Identify context indicators
            context_indicators = []

            # Look for relationship indicators around entity mentions
            for idx in occurrences:
                start = max(0, idx - 100)
                end = min(len(text), idx + len(entity_name) + 100)
                context = text[start:end].lower()

                # Common relationship indicators
                indicators = [
                    'met with', 'spoke with', 'discussed with', 'agreed with',
                    'announced', 'stated', 'said', 'commented', 'responded',
                    'leader', 'president', 'minister', 'director', 'ceo',
                    'company', 'organization', 'government', 'party'
                ]

                for indicator in indicators:
                    if indicator in context:
                        context_indicators.append(indicator)

            # Identify patterns
            patterns = []
            if re.search(r'\b(?:met|spoke|discussed|agreed)\s+with\b', text, re.IGNORECASE):
                patterns.append('collaboration')
            if re.search(r'\b(?:announced|stated|said|commented)\b', text, re.IGNORECASE):
                patterns.append('statement')
            if re.search(r'\b(?:president|minister|director|ceo)\b', text, re.IGNORECASE):
                patterns.append('role_title')

            relationships[entity_name] = {
                "frequency": frequency,
                "proximity": avg_proximity,
                "indicators": list(set(context_indicators)),
                "patterns": patterns
            }

        return relationships

    def _calculate_temporal_consistency(self, entity_name: str, current_date: str) -> float:
        """Calculate temporal consistency of entity mentions"""
        # Find all mentions of this entity across time
        consistency = 0.5  # Base consistency

        # Look for existing mentions of this entity
        entity_mentions = []
        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("node_type") == "article":
                entities = node_data["properties"].get("entities", {})
                for entity_type, entity_list in entities.items():
                    if entity_name in entity_list:
                        timestamp = node_data["properties"].get("published_date")
                        if timestamp:
                            entity_mentions.append(timestamp)

        if len(entity_mentions) > 1:
            # Calculate consistency based on time distribution
            dates = sorted([datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in entity_mentions])
            time_spans = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]

            if time_spans:
                avg_span = sum(time_spans) / len(time_spans)
                # Higher consistency for more regular mention patterns
                consistency = min(1.0, 30 / max(avg_span, 1))  # 30 days as reference

        return consistency

    def _calculate_source_reliability(self, article_data: dict[str, Any]) -> float:
        """Calculate reliability score for the article source"""
        reliability = 0.7  # Base reliability

        # Known reliable sources
        reliable_domains = {
            'bbc.co.uk', 'reuters.com', 'apnews.com', 'nytimes.com',
            'washingtonpost.com', 'theguardian.com', 'wsj.com',
            'ft.com', 'bloomberg.com', 'cnn.com', 'nbcnews.com'
        }

        domain = article_data.get("domain", "").lower()
        if domain in reliable_domains:
            reliability += 0.2

        # Publisher reputation
        publisher = article_data.get("publisher_meta", {}).get("publisher", "").lower()
        if publisher in ['bbc news', 'reuters', 'associated press', 'new york times']:
            reliability += 0.1

        return min(reliability, 1.0)

    def _calculate_cross_validation(self, entity_name: str, article_data: dict[str, Any]) -> float:
        """Calculate cross-validation score for entity mentions"""
        validation = 0.0

        # Check if entity appears in title
        title = article_data.get("title", "")
        if entity_name in title:
            validation += 0.3

        # Check for multiple mentions
        content = article_data.get("content", "")
        mention_count = content.count(entity_name)
        validation += min(mention_count / 5, 0.4)

        # Check for contextual consistency
        if re.search(r'\b(?:said|stated|announced|commented)\b.*' + re.escape(entity_name), content, re.IGNORECASE):
            validation += 0.3

        return min(validation, 1.0)

    def apply_entity_clustering(self, similarity_threshold: float = 0.8) -> dict[str, Any]:
        """
        Apply entity clustering to group similar entities in the knowledge graph

        Args:
            similarity_threshold: Minimum similarity score for clustering

        Returns:
            Clustering summary with statistics
        """
        logger.info("🔗 Applying entity clustering to knowledge graph...")

        # Update clustering threshold if different
        if similarity_threshold != self.entity_clustering.similarity_threshold:
            self.entity_clustering = EntityClustering(similarity_threshold)

        # Collect all entity names by type
        entities_by_type = {}
        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("node_type") == "entity":
                entity_type = node_data["properties"].get("entity_type", "unknown")
                entity_name = node_data["properties"].get("name", "")

                if entity_type not in entities_by_type:
                    entities_by_type[entity_type] = []
                entities_by_type[entity_type].append(entity_name)

        # Apply clustering for each entity type
        total_clusters = 0
        total_entities_clustered = 0
        cluster_details = {}

        for entity_type, entity_names in entities_by_type.items():
            if len(entity_names) < 2:
                continue

            logger.info(f"🎯 Clustering {len(entity_names)} {entity_type} entities...")

            # Cluster entities
            clusters = self.entity_clustering.cluster_entities(entity_names)

            # Apply clustering to graph
            merged_mapping = self.entity_clustering.merge_clusters(self.graph)

            cluster_details[entity_type] = {
                "original_entities": len(entity_names),
                "clusters_created": len(clusters),
                "entities_merged": len(merged_mapping),
                "clusters": clusters
            }

            total_clusters += len(clusters)
            total_entities_clustered += len(merged_mapping)

        # Save updated graph
        self._save_graph()

        summary = {
            "clustering_applied": True,
            "total_clusters": total_clusters,
            "total_entities_clustered": total_entities_clustered,
            "entity_types_processed": len(cluster_details),
            "cluster_details": cluster_details,
            "similarity_threshold": similarity_threshold,
            "graph_nodes_after_clustering": len(self.graph.nodes),
            "graph_edges_after_clustering": len(self.graph.edges)
        }

        logger.info("✅ Entity clustering completed!")
        logger.info(f"📊 Created {total_clusters} clusters, merged {total_entities_clustered} entities")

        return summary

    def get_clustering_statistics(self) -> dict[str, Any]:
        """
        Get statistics about entity clusters in the knowledge graph

        Returns:
            Clustering statistics
        """
        stats = {
            "total_entity_nodes": 0,
            "clustered_entities": 0,
            "clusters_by_type": {},
            "cluster_sizes": [],
            "average_cluster_size": 0,
            "largest_cluster": 0
        }

        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("node_type") == "entity":
                stats["total_entity_nodes"] += 1

                cluster_size = node_data["properties"].get("cluster_size", 1)
                if cluster_size > 1:
                    stats["clustered_entities"] += cluster_size

                    entity_type = node_data["properties"].get("entity_type", "unknown")
                    if entity_type not in stats["clusters_by_type"]:
                        stats["clusters_by_type"][entity_type] = 0
                    stats["clusters_by_type"][entity_type] += 1

                    stats["cluster_sizes"].append(cluster_size)
                    stats["largest_cluster"] = max(stats["largest_cluster"], cluster_size)

        if stats["cluster_sizes"]:
            stats["average_cluster_size"] = sum(stats["cluster_sizes"]) / len(stats["cluster_sizes"])

        return stats

    def _calculate_time_window(self, timestamp: str) -> str:
        """Calculate appropriate time window for temporal analysis"""
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            hour = dt.hour

            if 6 <= hour < 12:
                return "morning"
            elif 12 <= hour < 18:
                return "afternoon"
            elif 18 <= hour < 22:
                return "evening"
            else:
                return "night"
        except (ValueError, TypeError, AttributeError):
            return "unknown"

    def process_article(self, article_data: dict[str, Any]) -> dict[str, Any]:
        """
        Process a single article through the knowledge graph pipeline

        Args:
            article_data: Article data with content and metadata

        Returns:
            Processing summary
        """
        # Add article node
        article_node_id = self.add_article_node(article_data)

        # Extract and add entities
        entities = article_data.get("entities", {})
        if not entities and "content" in article_data:
            entities = self.entity_extractor.extract_entities(article_data["content"])

        entity_nodes = self.add_entity_nodes(entities)

        # Add relationships
        self.add_relationships(article_node_id, entity_nodes, article_data)

        # Save graph state
        self._save_graph()

        summary = {
            "article_node_id": article_node_id,
            "entities_extracted": len(entity_nodes),
            "entity_types": list(entities.keys()),
            "relationships_created": len(entity_nodes),
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges)
        }

        logger.info(f"✅ Processed article: {summary}")
        return summary

    def query_entities(self, entity_type: str = None, limit: int = 50) -> list[dict[str, Any]]:
        """
        Query entities in the knowledge graph

        Args:
            entity_type: Filter by entity type (PERSON, ORG, etc.)
            limit: Maximum number of results

        Returns:
            List of entity information
        """
        entities = []

        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("node_type") == "entity":
                if entity_type is None or node_data["properties"].get("entity_type") == entity_type:
                    entities.append({
                        "node_id": node_id,
                        **node_data["properties"]
                    })

                    if len(entities) >= limit:
                        break

        return entities

    def query_article_relationships(self, article_node_id: str) -> dict[str, Any]:
        """
        Query relationships for a specific article

        Args:
            article_node_id: ID of the article node

        Returns:
            Article relationships information
        """
        if article_node_id not in self.graph.nodes:
            return {"error": "Article node not found"}

        relationships = {
            "article_node": self.graph.nodes[article_node_id],
            "mentioned_entities": [],
            "temporal_relationships": []
        }

        # Get outgoing edges (article -> entities)
        for _, target_id, edge_type, edge_data in self.graph.out_edges(article_node_id, keys=True, data=True):
            if edge_type == "mentions":
                relationships["mentioned_entities"].append({
                    "entity_node_id": target_id,
                    "relationship": edge_data
                })

        # Get incoming temporal edges (entities -> article)
        for source_id, _, edge_type, edge_data in self.graph.in_edges(article_node_id, keys=True, data=True):
            if edge_type == "mentioned_at_time":
                relationships["temporal_relationships"].append({
                    "entity_node_id": source_id,
                    "relationship": edge_data
                })

        return relationships

    def get_graph_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about the knowledge graph"""
        stats = {
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "node_types": {},
            "edge_types": {},
            "entity_types": {},
            "temporal_coverage": {}
        }

        # Node type distribution
        for node_id, node_data in self.graph.nodes(data=True):
            node_type = node_data.get("node_type", "unknown")
            stats["node_types"][node_type] = stats["node_types"].get(node_type, 0) + 1

            if node_type == "entity":
                entity_type = node_data["properties"].get("entity_type", "unknown")
                stats["entity_types"][entity_type] = stats["entity_types"].get(entity_type, 0) + 1

        # Edge type distribution
        for _, _, edge_type, _ in self.graph.edges(keys=True, data=True):
            stats["edge_types"][edge_type] = stats["edge_types"].get(edge_type, 0) + 1

        return stats

class KnowledgeGraphManager:
    """
    High-level manager for Phase 3 knowledge graph operations

    Integrates with archive system and provides comprehensive KG functionality
    """

    def __init__(self, kg_storage_path: str = "./kg_storage"):
        self.kg = TemporalKnowledgeGraph(kg_storage_path)
        # Initialize entity linker for external knowledge base integration
        self.entity_linker = EntityLinkerManager(self.kg, cache_dir=str(Path(kg_storage_path) / "entity_cache"))
        logger.info("🎯 Phase 3 Knowledge Graph Manager initialized with entity linking")

    async def process_archive_batch(self, archive_summary: dict[str, Any],
                                  archive_manager) -> dict[str, Any]:
        """
        Process a batch of archived articles through the knowledge graph

        Args:
            archive_summary: Summary from archive batch operation
            archive_manager: Archive manager instance for retrieving articles

        Returns:
            Knowledge graph processing summary
        """
        storage_keys = archive_summary.get("storage_keys", [])

        if not storage_keys:
            logger.warning("⚠️ No storage keys found in archive summary")
            return {"error": "No articles to process"}

        logger.info(f"🧠 Processing {len(storage_keys)} archived articles through KG")

        processed_articles = []
        total_entities = 0

        for storage_key in storage_keys:
            try:
                # Retrieve article from archive
                article_data = await archive_manager.storage_manager.retrieve_article(storage_key)

                if article_data and "article_data" in article_data:
                    article = article_data["article_data"]

                    # Process through knowledge graph
                    kg_result = self.kg.process_article(article)

                    processed_articles.append({
                        "storage_key": storage_key,
                        "article_title": article.get("title", "Unknown"),
                        "kg_result": kg_result
                    })

                    total_entities += kg_result.get("entities_extracted", 0)

            except Exception as e:
                logger.error(f"Failed to process {storage_key}: {e}")
                continue

        summary = {
            "kg_processing": True,
            "articles_processed": len(processed_articles),
            "total_entities_extracted": total_entities,
            "avg_entities_per_article": total_entities / len(processed_articles) if processed_articles else 0,
            "graph_statistics": self.kg.get_graph_statistics(),
            "processed_articles": processed_articles,
            "timestamp": datetime.now().isoformat()
        }

        logger.info("✅ Knowledge graph batch processing complete!")
        logger.info(f"📊 Processed: {len(processed_articles)} articles")
        logger.info(f"🏷️ Entities extracted: {total_entities}")

        return summary

    async def enrich_entities_with_external_knowledge(self, limit: int = 100) -> dict[str, Any]:
        """
        Enrich entities in the knowledge graph with external knowledge bases

        Args:
            limit: Maximum number of entities to enrich

        Returns:
            Enrichment summary with statistics
        """
        logger.info(f"🔗 Starting entity enrichment with external knowledge bases (limit: {limit})")

        try:
            enrichment_result = await self.entity_linker.enrich_knowledge_graph_entities(limit)

            # Update graph statistics after enrichment
            enrichment_result["updated_graph_statistics"] = self.kg.get_graph_statistics()

            logger.info("✅ Entity enrichment with external knowledge bases complete!")
            return enrichment_result

        except Exception as e:
            logger.error(f"Entity enrichment failed: {e}")
            return {"error": str(e), "enrichment_failed": True}

    async def get_entity_external_info(self, entity_name: str, entity_type: str = None) -> dict[str, Any]:
        """
        Get external information for a specific entity

        Args:
            entity_name: Name of the entity to enrich
            entity_type: Optional entity type

        Returns:
            External entity information from knowledge bases
        """
        try:
            return await self.entity_linker.get_entity_external_info(entity_name, entity_type)
        except Exception as e:
            logger.error(f"Failed to get external info for {entity_name}: {e}")
            return {"error": str(e)}

    def get_entity_linking_statistics(self) -> dict[str, Any]:
        """
        Get statistics about entity linking and enrichment

        Returns:
            Entity linking statistics
        """
        return self.entity_linker.get_enrichment_statistics()

async def demo_phase3_kg():
    """Demonstrate Phase 3 knowledge graph capabilities"""

    print("🧠 Phase 3 Knowledge Graph Foundation Demo")
    print("=" * 60)

    # Initialize knowledge graph manager
    kg_manager = KnowledgeGraphManager()

    # Sample articles for demonstration
    sample_articles = [
        {
            "url": "https://www.bbc.co.uk/news/politics/sample-election-coverage",
            "url_hash": "sample1",
            "domain": "bbc.co.uk",
            "title": "Prime Minister Announces New Economic Policy",
            "content": "Prime Minister David Cameron announced a new economic policy today in London. The policy aims to boost growth in the UK economy. Business leaders from major corporations like BP and Shell have expressed support for the initiative. The announcement was made during a press conference at 10 Downing Street.",
            "timestamp": datetime.now().isoformat(),
            "publisher_meta": {"publisher": "BBC News"},
            "news_score": 0.8
        },
        {
            "url": "https://www.reuters.com/business/sample-tech-merger",
            "url_hash": "sample2",
            "domain": "reuters.com",
            "title": "Tech Giant Microsoft Acquires AI Startup",
            "content": "Microsoft Corporation announced today that it has acquired an AI startup based in San Francisco. The acquisition is valued at $2 billion. CEO Satya Nadella stated that this move strengthens Microsoft's position in artificial intelligence. The startup's technology will be integrated into Azure cloud services.",
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "publisher_meta": {"publisher": "Reuters"},
            "news_score": 0.9
        },
        {
            "url": "https://www.nytimes.com/world/sample-climate-summit",
            "url_hash": "sample3",
            "domain": "nytimes.com",
            "title": "World Leaders Gather for Climate Summit in Paris",
            "content": "World leaders from countries including the United States, China, and Germany gathered in Paris for the annual Climate Change Conference. President Joe Biden met with Chinese President Xi Jinping to discuss carbon emission reductions. The European Union representatives emphasized the need for immediate action on climate change.",
            "timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
            "publisher_meta": {"publisher": "The New York Times"},
            "news_score": 0.85
        }
    ]

    print("📄 Processing sample articles through knowledge graph...")

    # Process articles
    for i, article in enumerate(sample_articles, 1):
        print(f"\n🔄 Processing article {i}: {article['title'][:50]}...")
        result = kg_manager.kg.process_article(article)
        print(f"   ✅ Entities extracted: {result['entities_extracted']}")
        print(f"   🏷️ Entity types: {', '.join(result['entity_types'])}")

    # Display graph statistics
    print("\n📊 Knowledge Graph Statistics:")
    stats = kg_manager.kg.get_graph_statistics()
    print(json.dumps(stats, indent=2))

    # Query examples
    print("\n🔍 Query Examples:")

    # Query all entities
    entities = kg_manager.kg.query_entities(limit=10)
    print(f"\n🏷️ Sample Entities ({len(entities)} total):")
    for entity in entities[:5]:  # Show first 5
        print(f"   {entity['name']} ({entity['entity_type']}) - mentioned {entity['mention_count']} times")

    # Query specific entity type
    persons = kg_manager.kg.query_entities("PERSON", limit=5)
    print(f"\n👥 Persons ({len(persons)}):")
    for person in persons:
        print(f"   {person['name']} - mentioned {person['mention_count']} times")

    print("\n🎉 Phase 3 Knowledge Graph Demo Complete!")
    print("\n🚀 Key Features Demonstrated:")
    print("   ✅ Entity extraction from article content")
    print("   ✅ Knowledge graph node and relationship creation")
    print("   ✅ Temporal relationship tracking")
    print("   ✅ Graph storage and persistence")
    print("   ✅ Query capabilities for entities and relationships")

    print("\n🔬 Phase 3 Research Capabilities Established:")
    print("   📚 Entity linking and disambiguation")
    print("   ⏰ Temporal analysis of news events")
    print("   🔗 Relationship discovery and analysis")
    print("   📊 Graph analytics and visualization foundation")

if __name__ == "__main__":
    asyncio.run(demo_phase3_kg())
