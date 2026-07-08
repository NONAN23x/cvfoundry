# Email Contract

Use this whenever the workflow asks for an email after a resume run or for standalone outreach.

## Goal

Produce a deterministic, concise draft grounded in the tailored resume and the selected profile's `CV.md`.

## Inputs

- the selected profile's `CV.md` for canonical sender facts and links
- `config/email-policy.json`
- The active job description, if any
- The tailored resume artifacts, if they exist
- Workflow evidence about whether an application was already submitted

## Truth Rules

- Never claim an application was submitted unless the workflow or user explicitly confirms it.
- Never claim a referral, conversation, attachment, timeline, or availability window unless provided.
- Reuse only supported strengths that already appear in the tailored resume or can be directly traced to `CV.md`.
- Keep the email aligned to the same role focus as the resume. Do not introduce extra domains or tools just to sound broader.

## Required Output Files

When email drafting is requested, add these files to the run folder:

- `email-draft.md`
- `email-metadata.json`

## `email-metadata.json`

Write these fields:

- `mode`: `application_follow_up` or `direct_outreach`
- `company`
- `role`
- `recipientName`: empty string if unknown
- `recipientEmail`: empty string if unknown
- `subject`
- `resumeAttachmentExpected`: `true` or `false`
- `resumeArtifact`: relative path if known, else empty string
- `strengthSourceIds`: source IDs backing the strengths referenced in the draft
- `callToAction`

## `email-draft.md`

Write exactly this structure:

```md
Subject: <final subject>
To: <recipient email or placeholder>

<greeting>

<paragraph 1>

<paragraph 2>

<canonical signature>
```

## Subject Rules

- If the workflow confirms an application already exists, use:
  `Follow-up on <Role> application - <Name>`
- Otherwise use:
  `Interest in <Role> - <Name>`

## Body Template

Paragraph 1 must:

- state the role context
- mention the resume only if it exists or is actually being sent
- reference two or three truthful, role-relevant strengths

Paragraph 2 must:

- make one clear call to action
- offer to share more detail
- close politely without pressure

## Canonical Signature

Use the locked basics from `CV.md`:

- full name
- email
- phone
- LinkedIn
- GitHub

## Default Template

```md
Subject: Interest in <Role> - <Name>
To: <recipient email>

<Recipient Name or Hiring Team>,

I am reaching out regarding the <Role> opportunity at <Company>. Based on my background in <strength 1>, <strength 2>, and <strength 3 if needed>, I believe I can contribute meaningfully to the team.

If helpful, I would welcome the chance to discuss the role further and share any additional details. Thank you for your time and consideration.

<Name>
<Email> | <Phone>
LinkedIn: <LinkedIn URL>
GitHub: <GitHub URL>
```

If the workflow confirms an application was already submitted, replace the first sentence with a follow-up framing and use the follow-up subject line.
