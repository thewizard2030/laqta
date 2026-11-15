# Laqta — Trademark & Brand Guidelines

**Document Status:** Active Policy (MIT License Continuity)  
**Effective Target:** Release `v0.2.5` (and all Laqta releases under MIT)  
**Applicability:** First-Party Names, Wordmarks, Vector Logos, and Brand Assets

---

## 1. Purpose & Legal Principles

This policy establishes guidelines for the use of the **Laqta** brand names, logos, and visual identifiers.

The project seeks to **protect users from confusion and false endorsement while fully preserving the open-source freedom to fork, modify, and redistribute the software under the terms of its MIT copyright license**:

1. **Separation of Copyright and Trademark Rights:** Open-source software licenses like the **MIT License** grant broad permissions to copy, modify, merge, publish, distribute, sublicense, and sell copies of the software. However, **open-source software licenses do not grant trademark rights** (and the MIT License includes no trademark endorsement or grant).
2. **Project Brand Claim:** "Laqta", the Arabic wordmark "لقطة", and the official logos are trademarks and service marks claimed by the project maintainer (Mohamed Aboelela) to identify the official open-source project and its distributions. **No registered trademark status (such as `®`) is claimed** unless formal registration has been officially granted and independently verified by a competent trademark registry.
3. **Jurisdictional Realities:** Trademark law varies significantly across jurisdictions. For example, while common-law jurisdictions (such as the United States) recognize certain trademark rights arising through use in commerce, civil-law jurisdictions (such as Egypt and continental European countries) generally recognize trademark rights primarily through formal administrative registration, with unregistered marks protected under narrower unfair competition or commercial fraud doctrines. The project maintainer's trademark policy operates as a contractual and community guideline defining authorized brand use, rather than asserting a uniform statutory common-law status worldwide.
4. **Preventing Consumer Confusion and False Endorsement:** The primary objective of this policy is to ensure that users, creators, and customers know whether the software or service they receive originates directly from the official Laqta maintainer or from an independent third party.

---

## 2. Protected Brand Identifiers

This policy applies to all brand identifiers claimed by the Laqta project:

1. **Wordmarks:**
   - The Latin product name: **Laqta**
   - The Arabic product name: **لقطة** (meaning "a take / a cut")
2. **Graphic Logos & Icons:**
   - The official geometric logo mark (combining the geometric timeline "L", playback triangle, and three vertical frame cues).
   - All master vector and raster assets in `Laqta_Brand_Kit/` (including `laqta-app-icon`, `laqta-symbol`, `laqta-logo-dark`, `laqta-logo-light`, `laqta-brand-banner`, and associated icons).
3. **Official Project Identity:**
   - The official repository: `https://github.com/thewizard2030/laqta`
   - Official releases, packages, and binaries published directly by the project maintainer.

---

## 3. Forking, Distribution & Rebranding Guidelines

Under open-source principles, forking is a fundamental right. Mandatory rebranding is **not a universal statutory requirement of copyright law**, but rather a brand protection rule enforced to prevent consumer confusion, false endorsement, and trademark dilution in commerce.

### 3.1 Git Development Forks (No Rebranding Required)

- You **do not need to rebrand** if you fork the repository on GitHub, GitLab, or another Git forge for development, personal study, experimentation, bug fixing, or submitting pull requests to the upstream project.
- Standard developer repository naming (e.g. `username/laqta`) is standard practice and fully permitted, provided the repository does not falsely describe itself as the official project repository.

### 3.2 Downstream Operating System & Distribution Packages (Permitted with Attribution)

- Package maintainers for Linux distributions (such as Fedora, Debian, Arch, or Flatpak packagers) who package official releases—including applying standard packaging, configuration, security, or platform-compatibility patches—**may use the name "Laqta"** to identify the package.
- The packaging must accurately identify the packaging maintainer (e.g., _"Laqta package maintained by the Fedora Project"_).

### 3.3 Verbatim Redistribution of Official Builds (Permitted)

- You may redistribute verbatim, unmodified copies of official Laqta releases under the name "Laqta", provided you do not alter the code or brand assets and do not misrepresent yourself as the upstream maintainer.

### 3.4 Substantially Modified Products & Commercial Distributions (Rebranding Required)

If you distribute a substantially modified derivative product to the public, launch an independent commercial offering, or market a distinct software distribution based on Laqta:

1. **Choose a Distinct Primary Name:** You must choose a distinct primary product name that does not incorporate "Laqta" or "لقطة" as its main identifier.
2. **Replace Official Graphic Logos:** You must remove the official application icons and logo graphics from `Laqta_Brand_Kit/` and use your own visual branding.
3. **Accurate Provenance:** You may and should truthfully credit the origin of your code using factual descriptive language, as detailed in Section 4.

---

## 4. Nominative Fair Use & Factual Attribution

Truthful, factual statements regarding software lineage or interoperability are legally protected and fully welcomed by the project:

### 4.1 Factual Lineage & Provenance

- _Permitted:_ "Based on the open-source Laqta engine."
- _Permitted:_ "Forked from Laqta v0.2.0."
- _Permitted:_ "Derived from the Laqta open-source project."

### 4.2 Interoperability & Extensions

- _Permitted:_ "Transcription plugin for Laqta"
- _Permitted:_ "Speech model optimized for use with Laqta"
- _Permitted:_ "Video theme designed for Laqta"

### 4.3 Commentary, Review & Education

- _Permitted:_ Using the name "Laqta" in articles, documentation, reviews, podcast discussions, and educational walkthroughs analyzing the software.

---

## 5. False Endorsement & Prohibited Uses

The following actions are misleading and strictly prohibited:

1. **False Claims of Official Status:** Calling an unofficial fork, build, or service "Official Laqta", "Laqta Pro", "Laqta Enterprise", or "Laqta Cloud" when it is not published or maintained by the official project maintainer.
2. **Misleading Domain Names & Social Media Handles:** Registering domain names (e.g., `laqta-app.com`, `laqta-cloud.io`) or official-sounding social media handles (e.g., `@laqta_official`) without explicit written consent.
3. **Deceptive Commercial Endorsement:** Advertising commercial hosting, deployment, or technical support in a manner that falsely implies certification, partnership, or sponsorship by Mohamed Aboelela or the project maintainers.
4. **Altering Official Logos:** Distorting official logo geometry, altering brand gradient angles, or combining the official mark with third-party commercial logos.

---

## 6. Commercial Activity Under the MIT License

**Nothing in this policy restricts commercial activity permitted by the open-source MIT software license.**

Under the MIT License, you are entirely free to:

- Sell services, deployments, and commercial support for Laqta.
- Offer hosted SaaS instances or on-premises solutions using the software.
- Build, combine, and commercially distribute extensions, integrations, or derivative software under the permissive terms of the MIT License (preserving the MIT copyright and permission notice).

However, commercial offerings must be marketed under your own distinct corporate name (e.g., _"Acme Services: Enterprise Setup & Support for Laqta"_), ensuring that clients understand they are contracting with your independent company rather than the open-source project maintainers.

---

## 7. Inquiries & Permission Requests

For questions regarding brand usage or to request permission for specialized uses:

- **Repository Issues:** [https://github.com/thewizard2030/laqta/issues](https://github.com/thewizard2030/laqta/issues)
- **Security & Private Contact:** See [SECURITY.md](file:///home/thewizard/Qatta/SECURITY.md)
