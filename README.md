# Blueline — ERPNext Custom App

Custom Frappe/ERPNext application for:
- **General Innovations (Pvt) Ltd** (GIIN)
- **Blueline Enterprises (Pvt) Ltd** (BLIN)

## Features
- Sri Lanka Gazette Tax Invoice print formats (EOG 03-0219, effective July 2026)
- Custom fields for TIN, SVAT, branch code, bank details
- Auto-generating invoice serial numbers (YYMMM_QQQQ_XXXXX)
- Commission automation scripts
- Workflow configurations

## Requirements
- ERPNext >= 15.0.0
- Frappe >= 15.0.0

## Installation

```bash
bench get-app blueline https://github.com/Intech24biz/V15-Erpnext-.git
bench --site your-site.com install-app blueline
bench migrate
```

## Developer
**Sohail Zafar — NovixCore**

## License
MIT
