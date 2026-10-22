# Resume Skill integration

The recognizer explicitly loads `skills/resume-material-parser/SKILL.md`, versions the rules, and validates source ranges, field/object types and full descriptions. Imports offer keep existing, keep incoming, or retain complete alternatives under one record, including awards. Facts require separate conflict confirmation; ignores apply only to the current import.

Validation: 285 profile-module offline tests passed, including 15 Skill cases. The isolated browser test exercises identity confirmation, A/B preview, retain both, reload, version switching and preservation of originals/defaults. Existing profile editing UI was also checked. No real data is bundled.

Storage compatibility: no new database or bulk rewrite of confirmed imports. New imports carry a parser contract and retain whole-group references in the existing version service; old confirmed imports remain under their historical contract. Ordinary saves do not add versions. Startup does not normalize existing empty records solely to add metadata.

Limitations: model connections and complex PDF reading order can fail. Rejected evidence and ambiguous identities remain explicit; Markdown agreement does not prove the original document was converted perfectly. Never interpret these tests as universal resume accuracy or recruiting-site acceptance.
