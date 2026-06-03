from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from django.core.files.base import ContentFile
from decimal import Decimal, ROUND_HALF_UP
import io


VAT_MULTIPLIER = Decimal('1.20')
CENT = Decimal('0.01')


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _split_ttc(total_ttc):
    total_ttc = _money(total_ttc)
    total_ht = (total_ttc / VAT_MULTIPLIER).quantize(CENT, rounding=ROUND_HALF_UP)
    tva = _money(total_ttc - total_ht)
    return total_ht, tva, total_ttc


def _format_eur(value):
    return f"{_money(value):.2f} €"


def _build_invoice_lines(commande, styles):
    lignes = list(commande.lignes.select_related('produit'))
    if not lignes:
        montant_ht, tva, montant_ttc = _split_ttc(commande.montant_ttc)
        return [[
            Paragraph(commande.offre_label or "Prestation", styles['Normal']),
            _format_eur(montant_ht),
            _format_eur(tva),
            _format_eur(montant_ttc),
        ]]

    rows = []
    for ligne in lignes:
        total_ligne_ttc = _money(ligne.prix_unitaire) * ligne.quantite
        montant_ht, tva, montant_ttc = _split_ttc(total_ligne_ttc)
        designation = f"{ligne.quantite} x {ligne.produit.nom}"
        rows.append([
            Paragraph(designation, styles['Normal']),
            _format_eur(montant_ht),
            _format_eur(tva),
            _format_eur(montant_ttc),
        ])

    frais_livraison = _money(getattr(commande, 'frais_livraison', 0))
    if frais_livraison > 0:
        montant_ht, tva, montant_ttc = _split_ttc(frais_livraison)
        rows.append([
            Paragraph("Frais de livraison", styles['Normal']),
            _format_eur(montant_ht),
            _format_eur(tva),
            _format_eur(montant_ttc),
        ])

    return rows


def generate_invoice_pdf(facture):
    buffer = io.BytesIO()
    
    # Configuration du document de base avec des marges
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Styles personnalisés pour le texte
    style_title = ParagraphStyle(
        name='Title',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#2C3E50"),
        alignment=0 # Gauche
    )
    style_right = ParagraphStyle(
        name='Right',
        parent=styles['Normal'],
        alignment=2 # Droite
    )
    
    # --- 1. EN-TÊTE ---
    # ATHLO à gauche, Infos facture à droite
    header_data = [
        [Paragraph("<b>ATHLO</b>", style_title),
         Paragraph(f"<b>FACTURE</b><br/>Numéro : {facture.numero_facture}<br/>Date : {facture.date_emission.strftime('%d/%m/%Y')}", style_right)]
    ]
    header_table = Table(header_data, colWidths=[250, 260])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 40))
    
    # --- 2. BLOCS ADRESSES ---
    coach_name = facture.commande.coach.user.get_full_name()
    client_name = f"{facture.commande.client.prenom} {facture.commande.client.nom}"
    
    address_data = [
        [Paragraph(f"<b>Émetteur :</b><br/>{coach_name}<br/>Plateforme ATHLO", styles['Normal']),
         Paragraph(f"<b>Facturé à :</b><br/>{client_name}", styles['Normal'])]
    ]
    address_table = Table(address_data, colWidths=[250, 260])
    address_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(address_table)
    elements.append(Spacer(1, 40))
    
    # --- 3. TABLEAU DES PRESTATIONS ---
    montant_ttc = _money(facture.commande.montant_ttc)
    montant_ht, tva, montant_ttc = _split_ttc(montant_ttc)
    
    table_data = [
        ["Désignation", "Montant HT", "TVA (20%)", "Total TTC"],
    ]
    table_data.extend(_build_invoice_lines(facture.commande, styles))
    
    # Les largeurs font un total d'environ 510 (largeur dispo sur A4 avec marges)
    t = Table(table_data, colWidths=[210, 100, 100, 100])
    t.setStyle(TableStyle([
        # En-tête du tableau
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#ECF0F1")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'), # Désignation à gauche
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), # Montants à droite
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        # Lignes de données
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor("#BDC3C7")), # Bordure basse
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # --- 4. BLOC DES TOTAUX ---
    totals_data = [
        ["Total HT :", _format_eur(montant_ht)],
        ["TVA (20%) :", _format_eur(tva)],
        ["TOTAL TTC :", _format_eur(montant_ttc)]
    ]
    totals_table = Table(totals_data, colWidths=[100, 100])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), # Labels en gras
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#7F8C8D")), # Labels en gris
        ('FONTNAME', (1, -1), (1, -1), 'Helvetica-Bold'), # Montant TTC en gras
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor("#2C3E50")), # Ligne TTC en bleu foncé
        ('FONTSIZE', (0, -1), (-1, -1), 12), # Ligne TTC plus grande
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    # On aligne le tableau des totaux strictement à droite
    wrapper_data = [["", totals_table]]
    wrapper_table = Table(wrapper_data, colWidths=[310, 200])
    wrapper_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(wrapper_table)
    elements.append(Spacer(1, 50))
    
    # --- 5. PIED DE PAGE ---
    footer_style = ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        alignment=1, # Centré
        textColor=colors.HexColor("#7F8C8D"),
        fontSize=9,
        fontName='Helvetica-Oblique'
    )
    
    
    # Génération du fichier PDF
    doc.build(elements)
    
    buffer.seek(0)
    filename = f"facture_{facture.numero_facture}.pdf"
    facture.pdf_file.save(filename, ContentFile(buffer.read()), save=False)
