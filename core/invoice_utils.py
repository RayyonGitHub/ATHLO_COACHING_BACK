from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.core.files.base import ContentFile
import io

def generate_invoice_pdf(facture):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Header
    p.setFont("Helvetica-Bold", 20)
    p.drawString(100, 750, "ATHLO - FACTURE")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 730, f"Numéro : {facture.numero_facture}")
    p.drawString(100, 715, f"Date : {facture.date_emission.strftime('%d/%m/%Y')}")
    
    # Client & Coach
    p.drawString(100, 680, f"Coach : {facture.commande.coach.user.get_full_name()}")
    p.drawString(100, 665, f"Client : {facture.commande.client.prenom} {facture.commande.client.nom}")
    
    # Détails
    p.line(100, 650, 500, 650)
    p.drawString(100, 630, f"Désignation : {facture.commande.offre_label}")
    p.drawString(100, 610, f"Montant HT : {facture.commande.montant_ht} €")
    p.drawString(100, 590, f"TVA (20%) : {round(facture.commande.montant_ttc - facture.commande.montant_ht, 2)} €")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, 560, f"TOTAL TTC : {facture.commande.montant_ttc} €")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    filename = f"facture_{facture.numero_facture}.pdf"
    facture.pdf_file.save(filename, ContentFile(buffer.read()), save=False)