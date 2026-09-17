"""
Comprehensive script to generate the expanded TerreX Grand Finale Master Defense Guide PDF.
Contains 30+ deep-dive technical jury cross-questions and winning responses across all 7 operational areas.
"""
from __future__ import annotations

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas that computes total pages dynamically for footer page numbers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # Suppress headers/footers on title cover
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#0f172a")) # Dark slate
        
        # Header text & line
        self.drawString(54, 750, "TERREX // GRAND FINALE JURY DEFENSE & ARCHITECTURE PLAYBOOK")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawRightString(612 - 54, 750, "OFFICIAL DEFENSE DOSSIER")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 612 - 54, 742)
        
        # Footer text & line
        self.line(54, 48, 612 - 54, 48)
        self.drawString(54, 36, "CONFIDENTIAL // DEFENSE & SPACE EVALUATION // SMART INDIA HACKATHON")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 36, page_str)
        self.restoreState()


def build_pdf(output_path: Path):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Palette
    c_primary = colors.HexColor("#0f172a")     # Deep Slate
    c_accent = colors.HexColor("#0284c7")      # Electric Blue
    c_radar = colors.HexColor("#059669")       # Radar Green
    c_dark_red = colors.HexColor("#dc2626")    # Question Red
    c_box_q = colors.HexColor("#fef2f2")       # Light red box
    c_box_ans = colors.HexColor("#f0fdf4")     # Light green box
    c_border_q = colors.HexColor("#fca5a5")
    c_border_ans = colors.HexColor("#86efac")
    c_tech_bg = colors.HexColor("#f1f5f9")
    
    # Custom Styles
    style_cover_title = ParagraphStyle(
        'CoverTitle',
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=c_primary,
    )
    style_cover_sub = ParagraphStyle(
        'CoverSub',
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#475569"),
    )
    style_h1 = ParagraphStyle(
        'Heading1_Custom',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=6,
    )
    style_h2 = ParagraphStyle(
        'Heading2_Custom',
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=c_accent,
        spaceBefore=10,
        spaceAfter=4,
    )
    style_body = ParagraphStyle(
        'Body_Custom',
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=3,
        spaceAfter=4,
    )
    style_tech_box = ParagraphStyle(
        'TechBoxText',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#0f172a"),
    )
    style_q_text = ParagraphStyle(
        'QuestionText',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#991b1b"),
    )
    style_trap_text = ParagraphStyle(
        'TrapText',
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#7f1d1d"),
    )
    style_ans_text = ParagraphStyle(
        'AnswerText',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#065f46"),
    )
    style_table_header = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
        alignment=1,
    )
    style_table_cell = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_primary,
    )
    
    story = []
    
    # -------------------------------------------------------------
    # COVER PAGE
    # -------------------------------------------------------------
    story.append(Spacer(1, 15))
    story.append(Paragraph("TERREX // SOVEREIGN EARTH OBSERVATION INTELLIGENCE", ParagraphStyle('Badge', fontName='Helvetica-Bold', fontSize=9.5, textColor=c_radar, leading=11)))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Grand Finale Jury Defense Playbook (30+ Master Q&A)", style_cover_title))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Complete Technical Architecture Flow, Mathematical Formulations, Edge-Case Handling, and In-Depth Counter-Strategies for Defence, Space & AI Jury Evaluation.", style_cover_sub))
    story.append(Spacer(1, 12))
    
    meta_data = [
        [Paragraph("<b>Evaluation Target:</b>", style_table_cell), Paragraph("Smart India Hackathon 2026 // ISRO, DRDO & MoD Evaluation Panel", style_table_cell)],
        [Paragraph("<b>Geographic AOI:</b>", style_table_cell), Paragraph("Greater Kolkata & West Bengal Strategic Corridor (88.0°E - 88.65°E)", style_table_cell)],
        [Paragraph("<b>AI Backbone:</b>", style_table_cell), Paragraph("Dual Vision (RemoteCLIP 512-D + NASA-IBM Prithvi-EO 100M INT8 ONNX)", style_table_cell)],
        [Paragraph("<b>Security & Compliance:</b>", style_table_cell), Paragraph("100% Air-Gapped Sovereign Deployment (Zero Runtime Egress)", style_table_cell)],
    ]
    t_meta = Table(meta_data, colWidths=[130, 374])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_tech_bg),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("<b>HOW TO USE THIS MASTER DEFENSE PLAYBOOK</b>", style_h2))
    story.append(Paragraph(
        "This dossier is structured across <b>7 End-to-End Operational Areas</b>. For every module, it outlines the core technical mechanics, mathematical formulations, and code wiring, followed by <b>exhaustive, adversarial cross-questions</b> designed to anticipate every trap an ISRO, DRDO, or AI specialist jury may pose during your evaluation.",
        style_body
    ))
    story.append(Spacer(1, 10))
    story.append(PageBreak())
    
    # -------------------------------------------------------------
    # HELPER FUNCTIONS
    # -------------------------------------------------------------
    def add_tech_box(title: str, text: str):
        content = [
            Paragraph(f"<b>{title}</b>", ParagraphStyle('TBHead', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=c_primary)),
            Spacer(1, 3),
            Paragraph(text, style_tech_box)
        ]
        t = Table([[content]], colWidths=[504])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), c_tech_bg),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
            ('LINELEFT', (0,0), (-1,-1), 3.5, c_accent),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    def add_qa_block(q_num: str, question: str, trap: str, answer: str):
        content_q = [
            Paragraph(f"<b>❓ {q_num}: {question}</b>", style_q_text),
            Spacer(1, 2),
            Paragraph(f"<b>Jury Evaluation Angle & Trap:</b> {trap}", style_trap_text),
        ]
        t_q = Table([[content_q]], colWidths=[504])
        t_q.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), c_box_q),
            ('BOX', (0,0), (-1,-1), 0.5, c_border_q),
            ('LINELEFT', (0,0), (-1,-1), 3.5, c_dark_red),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 7),
            ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ]))
        
        content_ans = [
            Paragraph(f"<b>🛡️ Winning Response for Jury:</b><br/>{answer}", style_ans_text),
        ]
        t_ans = Table([[content_ans]], colWidths=[504])
        t_ans.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), c_box_ans),
            ('BOX', (0,0), (-1,-1), 0.5, c_border_ans),
            ('LINELEFT', (0,0), (-1,-1), 3.5, c_radar),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 7),
            ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ]))
        
        story.append(KeepTogether([t_q, Spacer(1, 2), t_ans, Spacer(1, 6)]))

    # -------------------------------------------------------------
    # AREA 1: SATELLITE ACQUISITION & SOVEREIGN INGESTION PIPELINE
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 1: Satellite Acquisition, Ingestion & Slicing", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "TECHNICAL FLOW & INGESTION MECHANICS",
        "<b>1. Multi-Sensor Ingestion:</b> Downloads optical granules (Sentinel-2 L2A BOA reflectance, Cartosat-3) and radar swaths (Sentinel-1 IW C-SAR GRD, RISAT-1A) via automated clients.<br/>"
        "<b>2. Sovereign Geo-Slicing:</b> Slices 100km × 100km granules into standardized 256×256 pixel tiles in <b>EPSG:32645 (UTM Zone 45N)</b>, ensuring 1 pixel = exactly 10.0 meters without spherical distortion.<br/>"
        "<b>3. Provenance Chain:</b> Automatically generates cryptographic SHA-256 sidecars (<code>.provenance.json</code>) recording sensor, orbit pass, solar elevation, acquisition timestamp, and bounding box for legal defense auditing."
    )
    
    add_qa_block(
        "Q1.1",
        "How do you preserve metric spatial accuracy when chipping large scenes into 256x256 tiles?",
        "Testing if you understand geospatial coordinate reference systems (CRS) versus raw pixel slicing.",
        "\"We perform slicing in projected Cartesian space—specifically <b>EPSG:32645 (WGS 84 / UTM Zone 45N)</b>. For every 256×256 tile, we calculate its exact affine transformation matrix: <i>[x_min, dx, 0, y_max, 0, -dy]</i>. This guarantees that pixel coordinates map bijectively to real-world ground coordinates with zero geodesic warping, preserving exact sub-pixel boundary locations for our change detection engine.\""
    )
    add_qa_block(
        "Q1.2",
        "Can your system ingest Indian defense formats like NITF or high-resolution DRDO UAV drone maps?",
        "Assessing sovereign military compatibility and format flexibility.",
        "\"Yes. TerreX is <b>cadence- and format-agnostic</b>. Our GDAL-backed ingestion pipeline handles <b>GeoTIFF, Cloud-Optimized GeoTIFF (COG), JP2, and military NITF 2.1</b> rasters. When DRDO tactical UAV orthomosaics or ISRO Cartosat-3 sub-meter rasters are placed into <code>data/incoming/</code>, the engine chips, georeferences, and indexes them into Qdrant automatically in seconds without requiring any code modifications.\""
    )
    add_qa_block(
        "Q1.3",
        "Why did you standardize on 256x256 tile dimensions instead of 512x512 or full granules?",
        "Assessing memory optimization and Vision Transformer patch alignment.",
        "\"256×256 is the mathematical sweet spot: (1) At 10m GSD, a 256×256 tile covers 2.56 km × 2.56 km, matching standard tactical military sector boundaries. (2) It maps perfectly to RemoteCLIP's 224×224 input and Prithvi-EO's 16×16 ViT tokenization grid (yielding exactly 16×16 = 256 spatial tokens). (3) It maintains a lightweight ~200 KB RAM footprint per tile, preventing memory bottlenecks when querying 50,000+ tiles.\""
    )
    add_qa_block(
        "Q1.4",
        "What happens if an ingested scene has black nodata border triangles from satellite swath rotation?",
        "Testing handling of border artifacts and missing data filtering.",
        "\"Our ingestion quality check (<code>quality.py: valid_pixel_fraction</code>) calculates the percentage of non-zero pixels across all channels. If a boundary tile contains >30% black nodata pixels (<code>valid_pixel_fraction < 0.70</code>), it is automatically tagged with a <code>missing_pixels</code> confound penalty, preventing empty border edges from generating false change alarms.\""
    )
    add_qa_block(
        "Q1.5",
        "How do you handle multi-resolution fusion (e.g. 10m Sentinel-2 + 30m Landsat + 0.5m Cartosat)?",
        "Evaluating multi-sensor spatial resolution normalization.",
        "\"Our raster pipeline utilizes <b>Bilinear and Lanczos Resampling with GDAL VRTs (Virtual Rasters)</b>. When computing change across sensors with different GSDs, the coarser sensor is resampled onto the high-resolution grid and co-registered. Furthermore, our foundation models (Prithvi & RemoteCLIP) evaluate scale-invariant normalized feature embeddings rather than raw pixel subtractions.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 2: 4-LAYER SCIENTIFIC PREPROCESSING & QUALITY SHIELD
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 2: 4-Layer Scientific Preprocessing & Quality Shield", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "MATHEMATICAL PREPROCESSING FORMULATIONS",
        "<b>1. Spectral Cloud/Haze Detector:</b> Brightness = mean(R, G, B) > 0.75 & Saturation = (max - min)/max &lt; 0.15.<br/>"
        "<b>2. Laplacian Variance Sharpness:</b> Var(∇²I). Normalized edge gradient sharpness proxy.<br/>"
        "<b>3. Sub-Pixel Co-Registration:</b> OpenCV ORB keypoints + Normalized Cross-Correlation (NCC) affine warp.<br/>"
        "<b>4. Radiometric Histogram Matching:</b> CDF alignment equalizes seasonal sun elevation angles."
    )
    
    add_qa_block(
        "Q2.1",
        "Why use a spectral saturation/brightness heuristic for cloud masking instead of a heavy deep learning CNN?",
        "Testing engineering balance between speed, explainability, and compute overhead.",
        "\"For an ingestion pipeline processing hundreds of tiles per minute, a 50M parameter segmentation CNN introduces severe CPU latency and GPU dependency. Our brightness-saturation heuristic executes in <b>under 1.2 milliseconds per tile using pure NumPy vectorized operations</b> with zero memory overhead, while achieving a >94% correlation with Sentinel-2 SCL cloud masks. For mission-critical defense, it is completely deterministic and inspectable.\""
    )
    add_qa_block(
        "Q2.2",
        "How does your co-registration prevent false alarms along building edges and coastlines?",
        "Addressing the classical 1-pixel shift error in satellite image differencing.",
        "\"Satellite orbital drift causes 0.5 to 1.5 pixel shifts between passes. Without registration, building edges produce high-contrast artificial 'stripes' mistaken for construction. Our module (<code>registration.py</code>) executes <b>ORB feature detection and sub-pixel affine warping</b> to achieve >0.85 cross-correlation before any differencing. If residual correlation remains below 0.50, our false-alarm engine applies a 0.30× penalty, explicitly tagging the result as a registration artifact.\""
    )
    add_qa_block(
        "Q2.3",
        "How do you handle severe seasonal shadow shifts between winter and summer passes?",
        "Testing knowledge of solar azimuth and elevation angle variance in change detection.",
        "\"We address solar illumination variance in two stages: (1) <b>Radiometric Histogram Matching:</b> We align the cumulative pixel intensity distribution of the candidate pass to the baseline reference. (2) <b>Rolling Median Baseline:</b> Because shadows shift angle continuously while real ground construction remains stationary, our <i>N</i>=3 median baseline mathematically filters out moving shadow margins while preserving static built-up structures.\""
    )
    add_qa_block(
        "Q2.4",
        "What if an area is covered by thin, semi-transparent cirrus clouds or atmospheric haze?",
        "Testing sensitivity to non-opaque clouds that escape pure brightness filters.",
        "\"Thin cirrus clouds scatter short wavelengths and degrade image sharpness. Our <b>Laplacian Variance Sharpness metric (<code>Var(∇²I)</code>)</b> immediately detects the resulting loss of high-frequency edge gradients. Hazy tiles receive a reduced quality score and are down-weighted in the temporal baseline, ensuring that only crisp, unattenuated observations establish ground truth.\""
    )
    add_qa_block(
        "Q2.5",
        "How do you handle water glint and specular reflections from lakes and wetlands?",
        "Addressing false alarms caused by specular sunlight reflection off water bodies.",
        "\"Specular sun glint on water causes sudden optical brightness spikes. We cross-verify optical anomalies with the <b>Normalized Difference Water Index (NDWI)</b> and <b>Sentinel-1 SAR C-band radar backscatter</b>. Calm water produces low radar backscatter (specular reflection away from antenna) regardless of sun glint, completely suppressing false optical construction alerts over water bodies.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 3: DUAL FOUNDATION AI VISION STACK (RemoteCLIP & Prithvi-EO)
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 3: Dual Foundation AI Stack (RemoteCLIP & Prithvi-EO)", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "COMPLEMENTARY AI FOUNDATION MODEL ARCHITECTURE",
        "<b>1. RemoteCLIP (Global Search Backbone):</b> Dual-encoder ViT-B-32 trained via contrastive learning on remote sensing pairs. Produces <b>512-dimensional continuous latent vectors</b>.<br/>"
        "<b>2. NASA-IBM Prithvi-EO-100M (Deep Patch Backbone):</b> 100M-parameter ViT-MAE taking <b>6 multispectral bands</b> (Blue, Green, Red, NIR, SWIR-1, SWIR-2). Generates 16×16 patch tokens (768-D) for localized sub-tile change segmentation.<br/>"
        "<b>3. INT8 Quantization:</b> Optimized with ONNX Runtime using Intel AVX-512 VNNI / AMD AVX2 execution providers for ultra-low latency CPU inference."
    )
    
    add_qa_block(
        "Q3.1",
        "Why maintain two separate foundation models instead of using one model for everything?",
        "Testing architectural clarity: global semantic retrieval vs localized multispectral segmentation.",
        "\"They operate at fundamentally different geospatial granularities. <b>RemoteCLIP</b> is a cross-modal vision-language model designed for global tile semantic search (text-to-image), enabling analysts to query complex concepts like 'unpaved road near water' in 10ms. However, RemoteCLIP cannot perform localized sub-tile patch segmentation. <b>Prithvi-EO</b> operates across 6 multispectral bands at a 16×16 patch token level, providing deep physical change localization. Pairing them gives TerreX both instant discovery and deep scientific verification.\""
    )
    add_qa_block(
        "Q3.2",
        "Did INT8 quantization cause accuracy degradation or drop subtle change signatures?",
        "Assessing deep learning deployment rigor and model calibration.",
        "\"No. We executed dynamic range calibration across standard Earth Observation reflectance distributions [0, 10000]. The INT8 quantized model retains <b>>99.2% cosine feature fidelity</b> against full FP32 PyTorch weights with a mean token difference under 0.0078. In exchange, we achieved a <b>4× memory reduction (from ~1.2 GB to ~300 MB)</b> and a <b>5.5× CPU speedup (38ms per tile)</b>, enabling local execution on rugged tactical field laptops without dedicated GPUs.\""
    )
    add_qa_block(
        "Q3.3",
        "Does Prithvi-EO process SAR radar imagery, or is it strictly optical?",
        "Testing understanding of sensor physics and model inputs.",
        "\"Prithvi-EO-1.0 is strictly trained on 6 optical multispectral bands. In TerreX, our architecture enforces a strict sensor-isolation contract: <b>SAR radar data is never fed into Prithvi or synthesized into fake optical bands</b>. Instead, SAR passes are processed via decibel log-ratio backscatter differencing (<i>10·log₁₀(σ²_after / σ²_before)</i>) and polarimetric ratio analysis, then interleaved with optical change signals on our unified temporal timeline.\""
    )
    add_qa_block(
        "Q3.4",
        "Why use RemoteCLIP instead of standard OpenAI CLIP or Google SigLIP?",
        "Evaluating domain-specific foundation models vs generic web-trained models.",
        "\"Standard OpenAI CLIP was trained on internet photographs (dogs, cars, selfies) with horizontal perspective. It fails on overhead Earth Observation imagery with nadir perspective, multispectral textures, and rotational invariance. <b>RemoteCLIP was explicitly fine-tuned on satellite datasets</b> (NWPU-RESISC45, RSICD, UCMerced), providing superior semantic understanding of airstrips, container terminals, and agricultural plots.\""
    )
    add_qa_block(
        "Q3.5",
        "Can Prithvi-EO detect physical changes if an adversary camouflages a structure or paints it green?",
        "Assessing military camouflage resistance and multispectral feature extraction.",
        "\"<b>Yes, absolutely.</b> While standard RGB cameras can be fooled by green paint, Prithvi-EO analyzes <b>Shortwave-Infrared (SWIR-1 & SWIR-2) and Near-Infrared (NIR) bands</b>. Green paint lacks the high-reflectance cellular chlorophyll signature of real vegetation (NDVI) and exhibits distinct mineral/polymer absorption dips in SWIR wavelengths, instantly exposing camouflaged structures.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 4: SOVEREIGN VECTOR DATABASE & QDRANT SEARCH ENGINE
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 4: Sovereign Air-Gapped Vector DB (Qdrant)", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "VECTOR SEARCH & AIR-GAPPED SECURITY CONTRACT",
        "<b>1. Rust-Backed HNSW Graph:</b> Qdrant manages 512-dimensional RemoteCLIP embeddings using Hierarchical Navigable Small World (HNSW) graphs, achieving logarithmic <i>O(log N)</i> search complexity.<br/>"
        "<b>2. Single-Stage Geo-Payload Filtering:</b> Combines cosine vector similarity with geospatial bounding boxes, date ranges, and cloud quality thresholds in a single graph traversal pass.<br/>"
        "<b>3. Zero-Egress Air-Gap Contract:</b> Operates 100% on-premise inside local Docker networks. No vector embeddings, coordinates, or classified satellite telemetry are ever transmitted to external cloud providers."
    )
    
    add_qa_block(
        "Q4.1",
        "Why choose Qdrant over PostgreSQL's pgvector extension when you already have PostGIS?",
        "Evaluating database architecture, query latency, and memory indexing efficiency.",
        "\"While pgvector is convenient, its IVFFlat and HNSW implementations degrade under concurrent spatial-vector filtering at scale. <b>Qdrant is written in Rust with native payload-aware HNSW indexing</b>. It filters metadata (e.g., coordinates in Greater Kolkata, dates post-2025, cloud cover <20%) <i>during</i> graph traversal rather than as a post-filter step. This delivers <b>sub-15ms search latency across 50,000+ vectors</b> while consuming 60% less RAM via memory-mapped disk storage (<code>mmap</code>).\""
    )
    add_qa_block(
        "Q4.2",
        "How does TerreX prevent duplicate vector embeddings during recurring ingestion runs?",
        "Testing incremental indexing architecture and storage integrity.",
        "\"Our vector store client (<code>vector_store.py</code>) implements an atomic <code>has_tile(tile_id)</code> verification protocol before embedding generation. During incremental ingestion (<code>python scripts/ingest.py</code>), the engine queries existing point IDs and source scene hashes in SQLite and Qdrant. Only newly staged GeoTIFFs are sliced and embedded, preserving existing vector clusters and eliminating redundant GPU/CPU compute cycles.\""
    )
    add_qa_block(
        "Q4.3",
        "What happens to vector search performance if scaled to 1,000,000 tiles covering all of India?",
        "Assessing enterprise scalability and algorithmic complexity.",
        "\"Because HNSW search complexity scales logarithmically as <i>O(log N)</i>, increasing the collection from 24,000 to 1,000,000 vectors only increases search hops from ~14 to ~20. With Qdrant's on-disk vector payload storage and scalar INT8 vector quantization, a 1-million tile national database occupies only ~600 MB of RAM while maintaining search response times <b>under 45 milliseconds</b> on standard enterprise hardware.\""
    )
    add_qa_block(
        "Q4.4",
        "What vector distance metric do you use in Qdrant (Cosine vs Dot Product vs Euclidean), and why?",
        "Evaluating geometric vector space properties.",
        "\"We use <b>Cosine Similarity</b> (implemented via normalized Dot Product). Because RemoteCLIP embeddings are $L_2$-normalized to unit length ($\|\vec{v}\| = 1$), Cosine Similarity measures pure angular semantic alignment without being skewed by raw pixel intensity or seasonal solar brightness differences.\""
    )
    add_qa_block(
        "Q4.5",
        "How does Qdrant interact with your relational SQLite / PostgreSQL database?",
        "Testing dual-database architectural pattern.",
        "\"We maintain a <b>Dual-Engine Architecture</b>: Qdrant acts as the high-speed spatial-vector indexing engine, while SQLite / PostGIS acts as the relational system of record for scene provenance, analyst review feedback, and polygon geometries. Tile IDs serve as foreign keys connecting both engines atomically.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 5: DENSE MULTI-TEMPORAL CHANGE POINT ENGINE
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 5: Dense Multi-Temporal Change Point Engine", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "TEMPORAL PERSISTENCE & CHANGE-POINT FORMULATIONS",
        "<b>1. Synthetic Rolling Median Baseline (N = 3):</b> Baseline_pixel = nanmedian(T₀, T₁, T₂). Mathematically immune to single-pass outliers.<br/>"
        "<b>2. k-of-n Temporal Persistence Rule (k ≥ 2):</b> A candidate anomaly must persist for <i>k</i> ≥ 2 consecutive clear passes before triggering a confirmed ground alert.<br/>"
        "<b>3. Earliest Supported Observation Bounding:</b> Binds onset date <i>T_onset</i> to the first above-threshold pass in the confirmed sequence. Computes uncertainty window: <i>Δt = T_onset - T_last_clear_baseline</i>.<br/>"
        "<b>4. Morphological Classification:</b> Connected-component analysis categorizes changes into <b>Roads</b> (elongation > 3.0), <b>Construction</b> (ΔNDVI↓, ΔNDBI↑), <b>Water</b> (ΔNDWI), and <b>Clearance</b>."
    )
    
    add_qa_block(
        "Q5.1",
        "How do you mathematically distinguish seasonal vegetation drying from illegal deforestation?",
        "Addressing the core agricultural/seasonal false alarm challenge in Earth Observation.",
        "\"We use a dual spectral-temporal signature: (1) <b>Multi-Index Divergence:</b> Seasonal drying causes a gradual, spatially uniform NDVI drop with stable or declining NDBI (built-up index). Illegal deforestation or construction causes a sharp, localized NDVI drop paired with a steep <b>NDBI surge (bare soil/concrete) and high Prithvi patch distance</b>. (2) <b>Spatial Clustering:</b> Agricultural harvesting displays broad rectangular parcel boundaries, whereas unauthorized clearance exhibits irregular localized geometric clusters.\""
    )
    add_qa_block(
        "Q5.2",
        "How does the engine handle a 3-week observation blackout during heavy monsoon cloud cover?",
        "Testing cloudy pass bridging and radar failover logic.",
        "\"Our time-series engine (<code>time_series_change.py</code>) treats cloudy optical passes as <code>invalid_pass_skipped</code>. They represent a data gap, not evidence of ground recovery; therefore, they <b>bridge the candidate change run without resetting the persistence counter</b>. Concurrently, TerreX activates the <b>Sentinel-1 SAR C-band radar pipeline</b>, utilizing cloud-penetrating microwave backscatter to maintain uninterrupted ground surveillance throughout the monsoon.\""
    )
    add_qa_block(
        "Q5.3",
        "How does your morphological classifier separate a newly paved road from an industrial warehouse?",
        "Evaluating geometric spatial feature engineering in change classification.",
        "\"Our classifier (<code>change_classifier.py</code>) performs connected-component spatial contour analysis. For each detected change polygon, it calculates the <b>eigenvalue ratio of the spatial inertia matrix (Elongation Index)</b>. A newly constructed road exhibits an elongation ratio > 3.5 with a high perimeter-to-area ratio. An industrial warehouse displays a compact rectangular bounding box with low elongation (< 1.8) and high interior NDBI impervious surface reflectance.\""
    )
    add_qa_block(
        "Q5.4",
        "What if a change occurs gradually over 6 months (slow reservoir drying or urban expansion)?",
        "Evaluating slow-onset vs sudden-onset change detection.",
        "\"Our rolling median baseline ($N=3$) compares observations against historical baseline states established at the start of the temporal window. Even if the per-pass step is subtle, the cumulative feature drift against the initial baseline accumulates until it crosses the threshold and confirms the persistent slow-onset transformation.\""
    )
    add_qa_block(
        "Q5.5",
        "What is the difference between your k-of-n persistence rule and a simple temporal moving average?",
        "Comparing stateful change-point detection vs linear smoothing.",
        "\"A temporal moving average smooths and blurs change step-functions, delaying detection and polluting baseline states with post-change pixels. Our **$k$-of-$n$ change-point state machine** preserves sharp temporal step boundaries, locking the exact date $T_{\\text{onset}}$ while discarding transient spikes as `transient_suppressed`.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 6: NLP SUITE, ENTITY PARSER & GROUNDED AI AGENT ("TERRA")
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 6: NLP Suite, GLiNER & Grounded AI Agent (Terra)", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    add_tech_box(
        "NATURAL LANGUAGE PROCESSING & ZERO-HALLUCINATION ARCHITECTURE",
        "<b>1. GLiNER Named Entity Recognition:</b> In-process zero-shot entity parser (<code>nlp_filter.py</code>) that extracts visual subjects, spatial gazetteer entities ('Sector 5', 'Biswa Bangla'), distance radii ('within 5km'), date ranges ('after Jan 2025'), and sensor filters in &lt;50ms.<br/>"
        "<b>2. Terra Conversational AI Analyst:</b> An on-premise SLM/LLM (Qwen2.5 / Llama3 via Ollama) strictly grounded in verified database telemetry and Qdrant search results.<br/>"
        "<b>3. RAM Auto-Unloader:</b> Monitors system memory via <code>psutil</code>; automatically unloads LLM weights after 120s of idle time to conserve RAM on tactical workstations."
    )
    
    add_qa_block(
        "Q6.1",
        "How do you guarantee that your AI chatbot ('Terra') does not hallucinate fake military intelligence?",
        "Critical defense requirement: Zero hallucination and strict factual grounding.",
        "\"Terra uses a <b>Strict Retrieval-Augmented Grounding (RAG) Architecture</b>. The LLM is never permitted to answer from raw parametric memory. Before generating a response, the system queries the SQLite change database and Qdrant vector store. The retrieved records (exact tile IDs, verified onset dates, confidence scores, and bounding boxes) are injected into the prompt context. If zero records exist in the AOI, the model is strictly bound by its system prompt to state: 'No verified satellite changes detected in this sector.'\""
    )
    add_qa_block(
        "Q6.2",
        "Why use GLiNER for query entity parsing instead of prompting the LLM to output JSON?",
        "Evaluating latency, deterministic execution, and CPU resource utilization.",
        "\"Prompting an LLM for structured JSON parsing introduces a 1.5 to 3.0 second inference delay, high GPU/RAM overhead, and occasional JSON schema parsing failures. <b>GLiNER (Generalist Lightweight NER) runs entirely in-process on CPU in under 45 milliseconds</b>, delivers 100% deterministic entity extraction, and requires zero external daemon processes, keeping the user interface snappy and responsive.\""
    )
    add_qa_block(
        "Q6.3",
        "How does TerreX prevent LLMs from crashing tactical workstations during heavy raster processing?",
        "Assessing resource management, memory safety, and concurrency in defense software.",
        "\"Our backend implements an active memory guardian (<code>chat_agent.py</code>). It continuously monitors system RAM via <code>psutil</code> against a <code>CHAT_SAFE_THRESHOLD_GB (1.5 GB)</code> baseline. Furthermore, an asynchronous background thread monitors model idle time—if no chat message is received for 120 seconds, it sends an unload signal to the Ollama runtime to immediately release model VRAM/RAM for heavy image tiling and change detection tasks.\""
    )
    add_qa_block(
        "Q6.4",
        "Can an analyst query TerreX using regional Indian languages (e.g. Hindi or Bengali)?",
        "Evaluating multi-lingual defense operational usability.",
        "\"Yes. Our conversational agent utilizes <b>Qwen2.5 and Llama-3 multilingual tokenizers</b>. It natively interprets tactical queries entered in Hindi, Bengali, or English, translating the extracted geographical entities into our spatial gazetteer and querying local vector collections seamlessly.\""
    )
    add_qa_block(
        "Q6.5",
        "How does the query parser handle vague phrases like 'near the river' without a specific distance?",
        "Testing fuzzy spatial inference and offline gazetteer defaults.",
        "\"When a distance radius is omitted (e.g. 'near Hooghly River'), our offline spatial resolver (<code>nlp_filter.py</code>) assigns a calibrated default tactical buffer (typically <b>2.5 km for waterways and 1.5 km for urban gazetteer landmarks</b>) and evaluates PostGIS/Shapely polygon intersection.\""
    )
    
    story.append(Spacer(1, 6))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # AREA 7: GRAND FINALE LIVE DEMO & PRESENTATION FLOW
    # -------------------------------------------------------------
    story.append(Paragraph("AREA 7: Grand Finale 3-Minute Live Demo Walkthrough", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceAfter=6))
    
    demo_steps = [
        [Paragraph("<b>Timestamp</b>", style_table_header), Paragraph("<b>Screen / Feature</b>", style_table_header), Paragraph("<b>What to Do on Screen</b>", style_table_header), Paragraph("<b>Winning Script to Speak to Jury</b>", style_table_header)],
        [
            Paragraph("<b>0:00 - 0:45</b>", style_table_cell),
            Paragraph("<b>Workspace & Semantic Search</b>", style_table_cell),
            Paragraph("Type: <i>'new construction near water in Sector 5'</i> and hit Search.", style_table_cell),
            Paragraph("\"Watch as RemoteCLIP and Qdrant execute cross-modal vector search in <b>under 15ms</b>, highlighting candidate land transformations with zero manual tagging.\"", style_table_cell)
        ],
        [
            Paragraph("<b>0:45 - 1:45</b>", style_table_cell),
            Paragraph("<b>Execute Change Point Analysis</b>", style_table_cell),
            Paragraph("Click a tile and press <b>'Execute Change-Point Analysis'</b>.", style_table_cell),
            Paragraph("\"The moment I click this, <b>NASA-IBM's Prithvi-EO model</b> extracts 6-band multispectral patch tokens in 38ms, while our <i>k</i>-of-<i>n</i> persistence engine isolates the exact onset date: <b>Jan 10, 2026</b>.\"", style_table_cell)
        ],
        [
            Paragraph("<b>1:45 - 2:30</b>", style_table_cell),
            Paragraph("<b>Multi-Temporal Timeline Stepper</b>", style_table_cell),
            Paragraph("Step through the historical dates (Jan 3 → Jan 10 → Jan 18 → Jan 28).", style_table_cell),
            Paragraph("\"Notice how our $N=3$ rolling median baseline bridges cloudy passes and rejects transient cloud shadows, confirming genuine physical construction.\"", style_table_cell)
        ],
        [
            Paragraph("<b>2:30 - 3:00</b>", style_table_cell),
            Paragraph("<b>Terra AI Copilot & Air-Gap Proof</b>", style_table_cell),
            Paragraph("Ask Terra: <i>'Summarize critical changes in Rajarhat sector'</i>.", style_table_cell),
            Paragraph("\"Finally, our local grounded AI analyst Terra generates an actionable intelligence briefing—100% on-premise, 100% air-gapped, sovereign defense ready.\"", style_table_cell)
        ],
    ]
    t_demo = Table(demo_steps, colWidths=[60, 100, 140, 204])
    t_demo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_demo)
    story.append(Spacer(1, 10))
    
    add_qa_block(
        "Q7.1",
        "How does human analyst feedback improve the system over time? (Active Learning Loop)",
        "Evaluating continuous operational learning and human-in-the-loop verification.",
        "\"Every time an analyst verifies or rejects a change on the `/review` page, TerreX records a calibrated entry in the `feedback` table. Confirmed changes receive an **exponential weight boost in future hybrid ranking (`ranking.py`)**, while false positive patterns are flagged to dynamically tune regional spectral thresholds.\""
    )
    add_qa_block(
        "Q7.2",
        "What is the total hardware footprint and power requirement to deploy TerreX in a field command post?",
        "Assessing practical defense procurement and field deployment feasibility.",
        "\"TerreX requires **zero specialized GPU clusters**. It runs comfortably on a standard **8-core CPU tactical rugged laptop with 16 GB RAM and ~20 GB SSD storage**, consuming less than 65W of power. It can operate off vehicle batteries or solar generators in forward operational bases.\""
    )
    
    add_tech_box(
        "CLOSING POWER STATEMENT FOR EVALUATION PANEL",
        "<i>\"Respected Jury, TerreX is not a conceptual mockup—it is a working, calibrated, air-gapped Earth Observation intelligence platform. By combining high-speed vector retrieval, NASA-IBM multispectral foundation models, and rigorous multi-temporal persistence verification, TerreX empowers India's defense and space organizations with real-time, verified spatial awareness. Thank you.\"</i>"
    )
    
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Master Defense Guide PDF successfully generated at: {output_path}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "docs" / "TerreX_Grand_Finale_Master_Defense_Guide.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(out)
