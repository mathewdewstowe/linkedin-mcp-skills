# Workday Fields

## Common Application Steps

- Start Your Application: Autofill with Resume, Apply Manually, Use My Last Application.
- Sign In: social buttons first, then Sign in with email.
- My Information: source, previous employer, country, legal name, address/city, email, phone.
- My Experience: work experience, education, certifications, languages, skills, Resume/CV, websites, social URLs.
- Application Questions: salary, notice period, eligibility, safeguarding, background, role-specific motivation.
- Voluntary Disclosures: gender or other optional demographic fields, plus required terms/privacy consent.
- Review: final editable summary and Submit button.

## Dropdown Tactics

- Workday commonly labels unanswered dropdowns `Select One Required`.
- After selecting an answer, the button name changes to the selected value, e.g. `No Required`.
- Re-snapshot after every dropdown selection.
- For multiple identical unanswered dropdowns, select the first remaining unanswered dropdown only when the current page order is clear.

## Resume Upload Tactics

- Try direct upload only if the browser automation exposes a file-attachment method.
- If `input[type="file"]` exists but no setter is exposed, click/activate Select files.
- If Select files does nothing in the in-app browser, run `open -R "<resume path>"` and ask the user to drag the file from Finder onto the Workday drop zone.
- Verify upload by checking for an uploaded filename, success alert, size, or automatic advance to the next step.
