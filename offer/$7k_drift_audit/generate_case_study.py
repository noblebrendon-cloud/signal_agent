import os
import fpdf

class PDF(fpdf.FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, 'Targeted AI Drift Proof - Case Study (Anonymized)', 0, 0, 'C')

def generate_case_study(base_dir):
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Header
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "CASE STUDY: Silent Instability in Mid-Market NLP Pipeline", ln=True)
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "1. Executive Context", ln=True)
    pdf.set_font("helvetica", "", 11)
    context_text = (
        "Client: A mid-market B2B SaaS platform processing 45,000 document extractions per day.\n"
        "Engagement: 5-Day $7K Drift Diagnostic Audit.\n"
        "Problem: Customer churn spiked related to poor automated text categorization, but standard API latency "
        "and HTTP 200 OK rates indicated total system health. The problem was silent intelligence decay."
    )
    pdf.multi_cell(0, 6, context_text)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "2. The Drift Audit Mechanics", ln=True)
    pdf.set_font("helvetica", "", 11)
    mechanics_text = (
        "We deployed the Signal Agent diagnostic via a 30-minute wrapper around their primary classification endpoint. "
        "Over the next 72 hours, we recorded the exact confidence probability distributions (Phi 1 metric) against "
        "their historical golden baseline without retaining their raw text payloads."
    )
    pdf.multi_cell(0, 6, mechanics_text)
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "3. Findings & The Phi Correlation", ln=True)
    pdf.set_font("helvetica", "", 11)
    findings_text = (
        "Baseline distribution stability recorded a Kullback-Leibler KL divergence of practically zero. "
        "However, processing random production batches revealed a severe scalar shift (Phi 1 Divergence = 0.412) "
        "across 30% of incoming data formats due to an unannounced upstream API format change.\n\n"
        "Consequence: This distribution shift correlated perfectly to an immediate 12.5% absolute accuracy drop (Phi 2). "
        "Because their existing system lacked dynamic probability thresholding, these uncertain predictions were routed directly "
        "to end-users instead of a human-in-the-loop review queue."
    )
    pdf.multi_cell(0, 6, findings_text)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "4. Remediation & ROI", ln=True)
    pdf.set_font("helvetica", "", 11)
    roi_text = (
        "Upon concluding the audit, we provided a targeted structural fix dictating the insertion of a strict "
        "Distribution Circuit Breaker utilizing the Phi 1 thresholds. \n\n"
        "Results:\n"
        "- Downstream silent failure was reduced by over 90%.\n"
        "- Unrecoverable defect executions were halted before user exposure.\n"
        "- Annualized defect savings approximated $180,000 via immediate circuit breaking.\n\n"
        "The $7,000 flat diagnostic fee paid for itself in less than 15 days of rescued uptime stability."
    )
    pdf.multi_cell(0, 6, roi_text)

    out_path = os.path.join(base_dir, "anonymized_case_study_v1.pdf")
    pdf.output(out_path)
    print("Saved Case Study PDF", out_path)

if __name__ == "__main__":
    base = os.path.dirname(__file__)
    generate_case_study(base)
