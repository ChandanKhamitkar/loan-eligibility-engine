INSERT INTO crawl_sources (lender, url) VALUES
    ('Tata Capital', 'https://www.tatacapital.com/personal-loan.html'),
    ('IDFC FIRST Bank', 'https://www.idfcfirst.bank.in/personal-banking/loans/personal-loan'),
    ('ICICI Bank', 'https://www.icici.bank.in/personal-banking/loans/personal-loan')
ON CONFLICT (url) DO NOTHING;
