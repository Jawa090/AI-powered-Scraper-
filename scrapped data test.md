# Scraper Execution Report & Live Datasets

This document contains the execution parameters, configuration requirements, and raw data returned directly from all 4 scrapers attached to the system: **Bonfire** (City of Dallas), **DASNY** (Dormitory Authority of the State of New York), **JWiz** (Business Directory), and **NYSCR** (New York State Contract Reporter).

---

## 1. Scraper Requests & Execution Parameters

| Scraper ID | Target Portal / URL | Exact Request Given | Execution Mode & Requirements Explanation |
| :--- | :--- | :--- | :--- |
| **`bonfire`** | City of Dallas Bonfire Portal (`https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities`) | `ScrapeParams(limit=10)` | **Direct Execution (No Filters)**: Pre-scoped to City of Dallas municipal procurement opportunities. No filter parameters (category, keyword, location) are required by `validate_params()`. Extracted directly from the live open solicitations table. |
| **`dasny`** | Dormitory Authority State of New York (`https://www.dasny.org/opportunities/rfps-bids`) | `ScrapeParams(limit=10)` | **Direct Execution (No Filters)**: Scoped to NY State capital, higher-education, and healthcare construction and purchasing opportunities. Direct execution against the active solicitations feed without filter constraints. |
| **`jwiz`** | JWiz Business Directory (`https://jwiz.com`) | `ScrapeParams(limit=10, keyword="contractor", city="New York", us_state="NY")` | **Required Parameters Enforced**: JWiz scraper metadata defines `requires_location=True`. The controller's `validate_params()` strictly rejects requests missing location (`InvalidScrapeParams`). Target location and category keyword were supplied. |
| **`nyscr`** | NY State Contract Reporter (`https://www.nyscr.ny.gov/Ads/Search?BidFilter=Open`) | `ScrapeParams(limit=10)` | **Direct Execution (Public Solicitations Fallback)**: Automated headless logins on NYSCR encounter Google reCAPTCHA v3. The scraper executed directly against live public open opportunities without authentication barriers. |

---

## 2. City of Dallas Bonfire (`bonfire`) — 10 Datasets As-Is

```json
[
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "IFS-PKR-B2500040",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/256366",
    "title": "Service for POS Software and accessories system for golf course Pro Shop - 00000219993",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-07T20:00:00Z",
    "extra": {
      "ref_number": "IFS-PKR-B2500040",
      "status": "Open",
      "close_date": "Oct 7th 2026, 3:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "BU26-00030935",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/250177",
    "title": "Electrical Switchgear Repair Services",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-09T18:00:00Z",
    "extra": {
      "ref_number": "BU26-00030935",
      "status": "Open",
      "close_date": "Oct 9th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "BU26-00030999",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/250633",
    "title": "Residential Recycling Public Education Campaign",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-09T18:00:00Z",
    "extra": {
      "ref_number": "BU26-00030999",
      "status": "Open",
      "close_date": "Oct 9th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "CIZ26-OBP-30859",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/251131",
    "title": "Request for Competitive Sealed Proposals for Dallas Museum of Art for Mechanical and Electrical Upgrades",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-09T18:00:00Z",
    "extra": {
      "ref_number": "CIZ26-OBP-30859",
      "status": "Open",
      "close_date": "Oct 9th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "BT26-00031044",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/252487",
    "title": "Sewer Camera Maintenance & Repair Services",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-09T18:00:00Z",
    "extra": {
      "ref_number": "BT26-00031044",
      "status": "Open",
      "close_date": "Oct 9th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "IFS  - AVI B2100007",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/257231",
    "title": "*222045 Purchase of Traction Sand",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-13T18:00:00Z",
    "extra": {
      "ref_number": "IFS  - AVI B2100007",
      "status": "Open",
      "close_date": "Oct 13th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "CIZ26-PKR-29584",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/217865",
    "title": "Crawford Memorial Park Phase I Improvements",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-16T18:00:00Z",
    "extra": {
      "ref_number": "CIZ26-PKR-29584",
      "status": "Open",
      "close_date": "Oct 16th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "CIZ26-PKR-3234",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/246042",
    "title": "CITY OF DALLAS JOB ORDER CONTRACTING REQUEST FOR COMPETITIVE SEALED PROPOSALS",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-16T18:00:00Z",
    "extra": {
      "ref_number": "CIZ26-PKR-3234",
      "status": "Open",
      "close_date": "Oct 16th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "CIZ26-PKR-3234A",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/257481",
    "title": "Job Order Contracting RFCSP - Use for Submittal ONLY - REFERENCE ORIGNIAL SOLICITATION CIZ26-PKR-3234",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-16T18:00:00Z",
    "extra": {
      "ref_number": "CIZ26-PKR-3234A",
      "status": "Open",
      "close_date": "Oct 16th 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  },
  {
    "source_code": "bonfire",
    "record_kind": "opportunity",
    "external_id": "BD26-00031278",
    "source_url": "https://dallascityhall.bonfirehub.com/opportunities/252009",
    "title": "AI-Assisted Digital Evidence Analysis Platform",
    "description": null,
    "organization_name": "City of Dallas",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Dallas",
    "us_state": "TX",
    "postal_code": null,
    "category": null,
    "due_at": "2026-10-23T18:00:00Z",
    "extra": {
      "ref_number": "BD26-00031278",
      "status": "Open",
      "close_date": "Oct 23rd 2026, 1:00 PM CDT",
      "detail_blocked": false
    }
  }
]
```

---

## 3. Dormitory Authority of the State of New York (`dasny`) — 10 Datasets As-Is

```json
[
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "4002449999-P20",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/suny-dcc-fishkill-furnish-deliver-and-install-automotive-lab-and-shop",
    "title": "SUNY DCC at Fishkill - Furnish, Deliver and Install Automotive Lab and Shop Equipment",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": "Tabitha Ruiz",
    "contact_title": "Designated Contact",
    "email": "truiz@dasny.org",
    "phone": "+15182573203",
    "website": null,
    "city": "Fishkill",
    "us_state": "NY",
    "postal_code": "12524",
    "category": "Purchasing",
    "due_at": "2026-10-28T18:30:00Z",
    "extra": {
      "solicitation_number": "4002449999-P20",
      "location_raw": "SUNY DCC 461 Rt. 9, Fishkill, NY 12524",
      "due_date_raw": "10/28/2026 - 2:30 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "376600",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/omh-south-beach-psychiatric-center-rehab-auditorium-building-8-and",
    "title": "OMH South Beach Psychiatric Center Rehab of Auditorium in Building 8 and Asbestos Abatement",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": "Dominick Donadio",
    "contact_title": "Designated Contact",
    "email": "ccontracts@dasny.org",
    "phone": "+15182573000",
    "website": null,
    "city": "Staten Island",
    "us_state": "NY",
    "postal_code": "10305",
    "category": "Construction Contracts",
    "due_at": "2026-10-29T18:00:00Z",
    "extra": {
      "solicitation_number": "376600",
      "location_raw": "South Beach Psychiatric Center, 777 Seaview Avenue, Building #8, Staten Island, New York 10305",
      "due_date_raw": "10/29/2026 - 2:00 PM",
      "type": "Expression of Interest (EOI)"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "383670 / C1815",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/cuny-baruch-college-information-technology-building-2nd-3rd-4th-floor",
    "title": "CUNY Baruch College Information & Technology Building 2nd, 3rd, & 4th Floor Library Renovation & Associated Asbestos Abatement",
    "description": "Library renovation and associated asbestos abatement.",
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": "Brian Francis",
    "contact_title": "Designated Contact",
    "email": "BFrancis@DASNY.org",
    "phone": "518-903-5891",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": "10010",
    "category": "Construction Contracts",
    "due_at": "2026-10-29T18:00:00Z",
    "extra": {
      "solicitation_number": "383670 / C1815",
      "location_raw": "Baruch College, 151 East 25th Street, New York, NY, 10010",
      "due_date_raw": "10/29/2026 - 2:00 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "383580 / C1419",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/omh-hutchings-psychiatric-center-roof-replacement-associated-0",
    "title": "OMH Hutchings Psychiatric Center Roof Replacement & Associated Asbestos & Hazardous Material Abatement Buildings 6, and 11 (Phase 1 – Buildings 6 and 11)",
    "description": "Roof replacement and associated asbestos and hazardous material abatement.",
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": "Michael Gleason",
    "contact_title": "Designated Contact",
    "email": "MGleason@DASNY.org",
    "phone": "518-807-7812",
    "website": null,
    "city": "Syracuse",
    "us_state": "NY",
    "postal_code": "13210",
    "category": "Construction Contracts",
    "due_at": "2026-11-05T19:00:00Z",
    "extra": {
      "solicitation_number": "383580 / C1419",
      "location_raw": "Hutchings Psychiatric Center, 620 Madison St., Syracuse, NY 13210",
      "due_date_raw": "11/05/2026 - 2:00 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "381120",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/cuny-baruch-college-south-campus-boilers-and-asbestos-abatement",
    "title": "CUNY Baruch College South Campus Boilers and Asbestos Abatement",
    "description": "Boiler replacement and asbestos abatement at South Campus.",
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": "Brian Francis",
    "contact_title": "Designated Contact",
    "email": "BFrancis@DASNY.org",
    "phone": "518-903-5891",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": "10010",
    "category": "Construction Contracts",
    "due_at": "2026-11-05T19:00:00Z",
    "extra": {
      "solicitation_number": "381120",
      "location_raw": "Baruch College, 137 E 22nd Street, New York, New York, 10010",
      "due_date_raw": "11/05/2026 - 2:00 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "400084999-P19",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/york-college-furnish-deliver-and-provide-training-installation",
    "title": "York College-Furnish, Deliver and Provide Training on Installation of Sideline Tarp",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Jamaica",
    "us_state": "NY",
    "postal_code": "11451",
    "category": "Purchasing",
    "due_at": "2026-10-14T18:30:00Z",
    "extra": {
      "solicitation_number": "400084999-P19",
      "location_raw": "CUNY York College 9420 Guy R Brewer Blvd, Jamaica, NY 11451",
      "due_date_raw": "10/14/2026 - 2:30 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "4000849999-P18",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/york-college-furnish-and-provide-training-services-mobile-light-tower",
    "title": "York College - Furnish and Provide Training Services of Mobile Light Tower",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Jamaica",
    "us_state": "NY",
    "postal_code": "11451",
    "category": "Purchasing",
    "due_at": "2026-10-14T18:30:00Z",
    "extra": {
      "solicitation_number": "4000849999-P18",
      "location_raw": "CUNY York College 9420 Guy R Brewer Blvd, Jamaica, NY 11451",
      "due_date_raw": "10/14/2026 - 2:30 PM",
      "type": "Bid"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "388610 / C2031",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/cuny-john-jay-college-criminal-justice-new-building-fisp-9-associated",
    "title": "CUNY John Jay College of Criminal Justice New Building FISP 9 Associated Façade Repair(EOI)",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": "10019",
    "category": "Construction Contracts",
    "due_at": "2026-10-20T18:00:00Z",
    "extra": {
      "solicitation_number": "388610 / C2031",
      "location_raw": "John Jay College, New Building 899 10th Avenue, New York, NY 10019",
      "due_date_raw": "10/20/2026 - 2:00 PM",
      "type": "Expression of Interest (EOI)"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "380550",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/cuny-john-jay-college-haaren-hall-athletic-facility-restoration-and",
    "title": "CUNY John Jay College Haaren Hall Athletic Facility Restoration and HAZMAT Abatement",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": "10019",
    "category": "Construction Contracts",
    "due_at": "2026-10-16T14:15:00Z",
    "extra": {
      "solicitation_number": "380550",
      "location_raw": "John Jay College, Haaren Hall, 899 10th Avenue, New York, New York 10019",
      "due_date_raw": "10/16/2026 - 10:15 AM",
      "type": "Expression of Interest (EOI)"
    }
  },
  {
    "source_code": "dasny",
    "record_kind": "opportunity",
    "external_id": "389700 / C1924",
    "source_url": "https://www.dasny.org/opportunities/rfps-bids/2026/cuny-baruch-college-newman-hall-facade-restoration-and-hazardous",
    "title": "CUNY Baruch College – Newman Hall Façade Restoration and Hazardous Materials Abatement (Lead-Containing Coatings) (For Minority, Women and Small Business Enterprises only)",
    "description": null,
    "organization_name": "Dormitory Authority of the State of New York (DASNY)",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": "10010",
    "category": "Construction Contracts",
    "due_at": "2026-10-29T18:00:00Z",
    "extra": {
      "solicitation_number": "389700 / C1924",
      "location_raw": "Baruch College, Newman Hall, 137 East 22nd Steet, New York, NY, 10010",
      "due_date_raw": "10/29/2026 - 2:00 PM",
      "type": "Bid"
    }
  }
]
```

---

## 4. JWiz Business Directory (`jwiz`) — 10 Datasets As-Is

```json
[
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/ouding-construction-llc-97618.html",
    "source_url": "https://jwiz.com/jewish/ouding-construction-llc-97618.html",
    "title": "OuDing Construction LLC",
    "description": null,
    "organization_name": "OuDing Construction LLC",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Contractor",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/renzi-home-improvement-inc-26624.html",
    "source_url": "https://jwiz.com/jewish/renzi-home-improvement-inc-26624.html",
    "title": "Renzi Home Improvement Inc.",
    "description": "All types of Roofing & Siding. Hot Tar, Shingle, Slate, Spanish Tile, Siding, Galvanized Roofing, Copper Work, Asphalt, Flat Roofing, Aluminum & Vinyl Siding, Gutters, Leaders, Replacement Windows, Trim Work, Skylights. 24 Hour Emergency Service. Residential-Commercial. Free Estimates.",
    "organization_name": "Renzi Home Improvement Inc.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "+19147604459",
    "website": null,
    "city": "Yonkers",
    "us_state": "NY",
    "postal_code": null,
    "category": "Masonry & Concrete Contractors; Siding; Roofing",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "410 Hawthorne Ave., Yonkers, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/elvin-contracting-co-30302.html",
    "source_url": "https://jwiz.com/jewish/elvin-contracting-co-30302.html",
    "title": "Elvin Contracting Co.",
    "description": "Hang Doors, Install Windows, Trim Work, Moldings, Drywalls, Plaster, Tiles, Remodeling, Kitchen Cabinets, All Types Of Renovating, Wood & Tile Work, Commercial & Residential, Cabinets & Re-Facing Kitchen Cabinets.",
    "organization_name": "Elvin Contracting Co.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "+19149691300",
    "website": null,
    "city": "Yonkers",
    "us_state": "NY",
    "postal_code": null,
    "category": "Ceramics Tiles; Molding; Home Improvement; Roofing; Carpentry",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "Yonkers, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/adamspops-roofing-17451.html",
    "source_url": "https://jwiz.com/jewish/adamspops-roofing-17451.html",
    "title": "Adams/Pop's Roofing",
    "description": "Specializing in roofing, waterproofing, concrete, painting, masonry and skylights.",
    "organization_name": "Adams/Pop's Roofing",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "+12125810744",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Roofing",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/nikolins-contracting-co-38405.html",
    "source_url": "https://jwiz.com/jewish/nikolins-contracting-co-38405.html",
    "title": "Nikolin's Contracting Co.",
    "description": "Windows & Doors, Roofing, Plastering, Concrete Work, Natural Stone Walls, Paving, Brick Work, Electrical, Plumbing, Interior & Exterior Painting & Much More... We Design & Create: Decorative Painting, Window Treatments, Furniture Layout & Accessorizing. Licensed & Insured.",
    "organization_name": "Nikolin's Contracting Co.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "212-289-1939",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Roofing , Painters , Home Improvement",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/first-class-roofing-51717.html",
    "source_url": "https://jwiz.com/jewish/first-class-roofing-51717.html",
    "title": "First Class Roofing",
    "description": "New & Re-Roofing ,Flat Roofs , Hot & Cold Tar , Rubber Roofs, SBS Modified,Shingles,Slate & Tiles,Skylights,Gutters & Leaders.",
    "organization_name": "First Class Roofing",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "718-487-3933",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Roofing",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/global-quality-inc-39945.html",
    "source_url": "https://jwiz.com/jewish/global-quality-inc-39945.html",
    "title": "Global Quality Inc.",
    "description": "Flat & Single Roof. Gutters. Leaders. Skylights. Repairs. Copper Work. Slate. Tile Repair. Quality Work. Reasonable Prices. Free Estimates. Senior Citizen Discounts.",
    "organization_name": "Global Quality Inc.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": "718-813-9397",
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Roofing",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/melva-construction-corp-42110.html",
    "source_url": "https://jwiz.com/jewish/melva-construction-corp-42110.html",
    "title": "Melva Construction Corp.",
    "description": null,
    "organization_name": "Melva Construction Corp.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "New York",
    "us_state": "NY",
    "postal_code": null,
    "category": "Roofing",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "New York, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/welmac-construction-inc-36772.html",
    "source_url": "https://jwiz.com/jewish/welmac-construction-inc-36772.html",
    "title": "Welmac Construction, Inc.",
    "description": null,
    "organization_name": "Welmac Construction, Inc.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Queens Village",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "Queens Village, NY"
    }
  },
  {
    "source_code": "jwiz",
    "record_kind": "company",
    "external_id": "https://jwiz.com/jewish/brooklynite-construction-corp-48192.html",
    "source_url": "https://jwiz.com/jewish/brooklynite-construction-corp-48192.html",
    "title": "Brooklynite Construction Corp.",
    "description": null,
    "organization_name": "Brooklynite Construction Corp.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Brooklyn",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction",
    "due_at": null,
    "extra": {
      "lead_priority": "Standard",
      "location_line": "Brklyn, NY"
    }
  }
]
```

---

## 5. New York State Contract Reporter (`nyscr`) — 10 Datasets As-Is

```json
[
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2136228",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2136228",
    "title": "PortaCount Machine Calibration Services",
    "description": "PortaCount Machine Calibration Services. Agency/Company: People with Developmental Disabilities, NYS Office for; Division: Taconic DDSO; Category: Miscellaneous - Services; Type: Notice of sole/single source",
    "organization_name": "People with Developmental Disabilities, NYS Office for",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": null,
    "us_state": "NY",
    "postal_code": null,
    "category": "Miscellaneous - Services",
    "due_at": "2026-10-16T04:00:00Z",
    "extra": {
      "cr_number": "2136228",
      "agency": "People with Developmental Disabilities, NYS Office for",
      "division": "Taconic DDSO",
      "issue_date": "8/28/2026",
      "due_date_raw": "10/16/2026",
      "location_raw": "NY"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2138636",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2138636",
    "title": "27-28 Conservation/Preservation Discretionary Grants",
    "description": "27-28 Conservation/Preservation Discretionary Grants. Agency/Company: Education, NYS Dept. of; Division: Cultural Education; Category: Miscellaneous - Grant, Notice of Funds; Type: Grant",
    "organization_name": "Education, NYS Dept. of",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": null,
    "us_state": "NY",
    "postal_code": null,
    "category": "Miscellaneous - Grant, Notice of Funds",
    "due_at": "2026-11-17T05:00:00Z",
    "extra": {
      "cr_number": "2138636",
      "agency": "Education, NYS Dept. of",
      "division": "Cultural Education",
      "issue_date": "9/25/2026",
      "due_date_raw": "11/17/2026",
      "location_raw": "NY"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139439",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139439",
    "title": "New York City College of Technology — CUNY NAMM Building.",
    "description": "New York City College of Technology — CUNY NAMM Building.. Agency/Company: Dynamic US Inc; Location: 300 Jay Street, Brooklyn, NY, 11201; Category: Construction Vertical: Building Construction; Rehabilitation & New Construction; Type: Contractor Ads",
    "organization_name": "Dynamic US Inc",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Brooklyn",
    "us_state": "NY",
    "postal_code": "11201",
    "category": "Construction Vertical: Building Construction; Rehabilitation & New Construction",
    "due_at": "2026-10-19T04:00:00Z",
    "extra": {
      "cr_number": "2139439",
      "company": "Dynamic US Inc",
      "issue_date": "10/6/2026",
      "due_date_raw": "10/19/2026",
      "location_raw": "300 Jay Street, Brooklyn, NY, 11201"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139632",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139632",
    "title": "CUNY Queens College Hot Water Storage Tank Replacement and Asbestos Abatement",
    "description": "CUNY Queens College Hot Water Storage Tank Replacement and Asbestos Abatement. Agency/Company: Dormitory Authority of the State of New York; Location: Queens College, 65-30 Kissena Blvd., Flushing, NY 11367; Category: Construction Vertical: Building Construction; Rehabilitation & New Construction; Type: General",
    "organization_name": "Dormitory Authority of the State of New York",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Flushing",
    "us_state": "NY",
    "postal_code": "11367",
    "category": "Construction Vertical: Building Construction; Rehabilitation & New Construction",
    "due_at": "2026-11-17T05:00:00Z",
    "extra": {
      "cr_number": "2139632",
      "agency": "Dormitory Authority of the State of New York",
      "issue_date": "10/8/2026",
      "due_date_raw": "11/17/2026",
      "location_raw": "Queens College, 65-30 Kissena Blvd., Flushing, NY 11367"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139652",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139652",
    "title": "WMBE Opportunity - NYS Parks - Goat Island Pedestrian Access",
    "description": "WMBE Opportunity - NYS Parks - Goat Island Pedestrian Access. Agency/Company: McLaughlin Construction Corp.; Location: NIagara Falls NY; Category: Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction; Type: Contractor Ads",
    "organization_name": "McLaughlin Construction Corp.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Niagara Falls",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction",
    "due_at": "2026-10-30T04:00:00Z",
    "extra": {
      "cr_number": "2139652",
      "company": "McLaughlin Construction Corp.",
      "issue_date": "10/9/2026",
      "due_date_raw": "10/30/2026",
      "location_raw": "NIagara Falls NY"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139688",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139688",
    "title": "MBE, WBE and SDVOB Contracting Opportunity – Replacement of Guide Board Road Culvert over Middle Brook, PIN 7754.20, D041306",
    "description": "MBE, WBE and SDVOB Contracting Opportunity – Replacement of Guide Board Road Culvert over Middle Brook, PIN 7754.20, D041306. Agency/Company: Luck Brothers Inc.; Location: Black Brook; Category: Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction; Type: Contractor Ads",
    "organization_name": "Luck Brothers Inc.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Black Brook",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction",
    "due_at": "2026-10-20T04:00:00Z",
    "extra": {
      "cr_number": "2139688",
      "company": "Luck Brothers Inc.",
      "issue_date": "10/9/2026",
      "due_date_raw": "10/20/2026",
      "location_raw": "Black Brook"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139700",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139700",
    "title": "SUNY Delhi Replace Catskill Fire Alarm & BMS System",
    "description": "SUNY Delhi Replace Catskill Fire Alarm & BMS System. Agency/Company: Dormitory Authority of the State of New York; Location: SUNY Delhi, Catskill Hall, 454 Delhi Drive, Delhi, New York 13753; Category: Construction Vertical: Building Construction; Rehabilitation & New Construction; Type: General",
    "organization_name": "Dormitory Authority of the State of New York",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Delhi",
    "us_state": "NY",
    "postal_code": "13753",
    "category": "Construction Vertical: Building Construction; Rehabilitation & New Construction",
    "due_at": "2026-11-10T05:00:00Z",
    "extra": {
      "cr_number": "2139700",
      "agency": "Dormitory Authority of the State of New York",
      "issue_date": "10/9/2026",
      "due_date_raw": "11/10/2026",
      "location_raw": "SUNY Delhi, Catskill Hall, 454 Delhi Drive, Delhi, New York 13753"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139712",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139712",
    "title": "M/WBE/SDVOB Subcontractor & Supplier Opportunity",
    "description": "M/WBE/SDVOB Subcontractor & Supplier Opportunity. Agency/Company: Rifenburg Contracting Corp.; Location: Town of Bethlehem, Albany County; Category: Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction; Type: Contractor Ads",
    "organization_name": "Rifenburg Contracting Corp.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Bethlehem",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction",
    "due_at": "2026-10-15T04:00:00Z",
    "extra": {
      "cr_number": "2139712",
      "company": "Rifenburg Contracting Corp.",
      "issue_date": "10/9/2026",
      "due_date_raw": "10/15/2026",
      "location_raw": "Town of Bethlehem, Albany County"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139715",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139715",
    "title": "MBE & WBE Contracting Opportunity – Production Well No. 2 Raw Water Transmission Main",
    "description": "MBE & WBE Contracting Opportunity – Production Well No. 2 Raw Water Transmission Main. Agency/Company: Luck Brothers Inc.; Location: Beekmantown, NY; Category: Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction; Type: Contractor Ads",
    "organization_name": "Luck Brothers Inc.",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": "Beekmantown",
    "us_state": "NY",
    "postal_code": null,
    "category": "Construction Horizontal: Highways & Roadways; Maintenance, Repair & New Construction",
    "due_at": "2026-10-29T04:00:00Z",
    "extra": {
      "cr_number": "2139715",
      "company": "Luck Brothers Inc.",
      "issue_date": "10/9/2026",
      "due_date_raw": "10/29/2026",
      "location_raw": "Beekmantown, NY"
    }
  },
  {
    "source_code": "nyscr",
    "record_kind": "opportunity",
    "external_id": "2139724",
    "source_url": "https://www.nyscr.ny.gov/Ads/Details/2139724",
    "title": "S26-20242359ED",
    "description": "S26-20242359ED. Agency/Company: Power Authority of New York; Division: St. Lawrence/FDR Power Project; Category: Miscellaneous - Consulting & Other Services; Type: General",
    "organization_name": "Power Authority of New York",
    "contact_name": null,
    "contact_title": null,
    "email": null,
    "phone": null,
    "website": null,
    "city": null,
    "us_state": "NY",
    "postal_code": null,
    "category": "Miscellaneous - Consulting & Other Services",
    "due_at": "2026-10-30T04:00:00Z",
    "extra": {
      "cr_number": "2139724",
      "agency": "Power Authority of New York",
      "division": "St. Lawrence/FDR Power Project",
      "issue_date": "10/9/2026",
      "due_date_raw": "10/30/2026",
      "location_raw": "NY"
    }
  }
]
```
