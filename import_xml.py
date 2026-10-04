"""Import JATS XML files into database"""
import hashlib
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


def strip_ns(tag):
    """Remove namespace from XML tag"""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def get_text(element):
    """Get all text from an element and its children"""
    if element is None:
        return ""
    text = element.text or ""
    for child in element:
        text += get_text(child)
        if child.tail:
            text += child.tail
    return text.strip()


def parse_jats_xml(xml_path):
    """Parse JATS XML and extract structured data"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Handle pmc-articleset wrapper
    if strip_ns(root.tag) == 'pmc-articleset':
        article = root.find('.//{*}article')
    else:
        article = root
    
    if article is None:
        return None
    
    result = {
        'title': '',
        'authors': '',
        'abstract': '',
        'keywords': '',
        'paragraphs': [],
        'figures': [],
        'tables': [],
        'references': [],
    }
    
    # === Extract metadata from <front> ===
    front = article.find('{*}front')
    if front is not None:
        # Title
        title_elem = front.find('.//{*}article-title')
        if title_elem is not None:
            result['title'] = get_text(title_elem)
        
        # Authors
        contribs = front.findall('.//{*}contrib-group/{*}contrib')
        authors = []
        for contrib in contribs:
            name = contrib.find('{*}name')
            if name is not None:
                surname = name.find('{*}surname')
                given = name.find('{*}given-names')
                if surname is not None and given is not None:
                    authors.append(f"{get_text(given)} {get_text(surname)}")
        result['authors'] = ', '.join(authors[:10])  # First 10 authors
        
        # Abstract
        abstract_elems = front.findall('.//{*}abstract')
        abstract_texts = []
        for abs_elem in abstract_elems:
            # Skip graphical abstract
            if abs_elem.get('abstract-type') == 'graphical':
                continue
            for p in abs_elem.findall('{*}p'):
                text = get_text(p)
                if text:
                    abstract_texts.append(text)
        result['abstract'] = ' '.join(abstract_texts)[:2000]
        
        # Keywords
        kwd_group = front.find('.//{*}kwd-group')
        if kwd_group is not None:
            kwds = []
            for kwd in kwd_group.findall('{*}kwd'):
                kwd_text = get_text(kwd)
                if kwd_text:
                    kwds.append(kwd_text)
            result['keywords'] = ', '.join(kwds)
    
    # === Extract body paragraphs ===
    body = article.find('{*}body')
    if body is not None:
        para_seq = 0
        
        def process_sec(sec, section_title="", depth=0):
            nonlocal para_seq
            
            # Get section title
            title_elem = sec.find('{*}title')
            if title_elem is not None:
                section_title = get_text(title_elem)
            
            # Process paragraphs in this section
            for p in sec.findall('{*}p'):
                text = get_text(p)
                if text and len(text.strip()) > 20:
                    result['paragraphs'].append({
                        'section': section_title,
                        'text': text,
                        'sequence': para_seq,
                        'depth': depth,
                    })
                    para_seq += 1
            
            # Process subsections
            for subsec in sec.findall('{*}sec'):
                process_sec(subsec, section_title, depth + 1)
        
        # Process all top-level sections
        for sec in body.findall('{*}sec'):
            process_sec(sec)
    
    # === Extract figures ===
    figs = article.findall('.//{*}fig')
    for fig in figs:
        fig_id = fig.get('id', '')
        label = fig.find('{*}label')
        caption = fig.find('{*}caption')
        
        fig_data = {
            'fig_id': fig_id,
            'label': get_text(label) if label is not None else '',
            'caption': get_text(caption) if caption is not None else '',
        }
        result['figures'].append(fig_data)
    
    # === Extract tables ===
    table_wraps = article.findall('.//{*}table-wrap')
    for tw in table_wraps:
        tw_id = tw.get('id', '')
        label = tw.find('{*}label')
        caption = tw.find('{*}caption')
        
        table_data = {
            'table_id': tw_id,
            'label': get_text(label) if label is not None else '',
            'caption': get_text(caption) if caption is not None else '',
        }
        result['tables'].append(table_data)
    
    # === Extract references ===
    ref_list = article.find('.//{*}ref-list')
    if ref_list is not None:
        for ref in ref_list.findall('{*}ref'):
            ref_id = ref.get('id', '')
            # Get citation text
            mixed_citation = ref.find('{*}mixed-citation')
            if mixed_citation is not None:
                ref_text = get_text(mixed_citation)
            else:
                ref_text = get_text(ref)
            
            if ref_text:
                result['references'].append({
                    'ref_id': ref_id,
                    'text': ref_text[:500],
                })
    
    return result


def import_xml_to_db():
    db_path = 'data/research.db'
    xml_dir = Path('documents_xml')
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Add parse_engine column if not exists
    try:
        c.execute("ALTER TABLE papers ADD COLUMN parse_engine TEXT DEFAULT 'docling'")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE paragraphs ADD COLUMN parse_engine TEXT DEFAULT 'docling'")
    except:
        pass
    
    xml_files = list(xml_dir.glob('*.xml'))
    print(f"Found {len(xml_files)} XML files")
    
    success = 0
    failed = 0
    
    for xml_file in xml_files:
        pmc_id = xml_file.stem
        
        try:
            data = parse_jats_xml(xml_file)
            
            if data is None or not data['title']:
                print(f"  ⚠️  {pmc_id}: No title found, skipping")
                failed += 1
                continue
            
            # Generate paper_id
            paper_hash = hashlib.md5(pmc_id.encode()).hexdigest()[:8]
            paper_id = f"paper_{pmc_id}_{paper_hash}_xml"
            
            # Insert paper record
            c.execute("""
                INSERT OR REPLACE INTO papers 
                (paper_id, filename, title, abstract, authors, parse_engine)
                VALUES (?, ?, ?, ?, ?, 'xml')
            """, (paper_id, f"{pmc_id}.xml", data['title'], data['abstract'], data['authors']))
            
            # Insert paragraphs
            for i, para in enumerate(data['paragraphs']):
                para_id = f"{paper_id}_para_{i:05d}"
                c.execute("""
                    INSERT OR REPLACE INTO paragraphs
                    (para_id, paper_id, section_level1, text, sequence, parse_engine)
                    VALUES (?, ?, ?, ?, ?, 'xml')
                """, (para_id, paper_id, para['section'], para['text'], para['sequence']))
            
            print(f"  ✅ {pmc_id}: {len(data['paragraphs'])} paragraphs, {len(data['figures'])} figs, {len(data['tables'])} tables, {len(data['references'])} refs")
            success += 1
            
        except Exception as e:
            print(f"  ❌ {pmc_id}: {str(e)[:100]}")
            failed += 1
    
    conn.commit()
    
    # Print stats
    c.execute("SELECT parse_engine, COUNT(*) FROM papers GROUP BY parse_engine")
    print("\n" + "="*80)
    print("Paper counts by parse_engine:")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]} papers")
    
    c.execute("SELECT parse_engine, COUNT(*) FROM paragraphs GROUP BY parse_engine")
    print("\nParagraph counts by parse_engine:")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]} paragraphs")
    
    conn.close()
    
    print("\n" + "="*80)
    print(f"✅ Success: {success}")
    print(f"❌ Failed: {failed}")


if __name__ == "__main__":
    import_xml_to_db()
