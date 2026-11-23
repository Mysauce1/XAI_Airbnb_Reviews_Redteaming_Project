# Annotation Guidelines

These guidelines describe how the guest reviews in this project are annotated. Follow them when adding or changing labels in `data/annotations/annotations.csv`, so that every review is labelled the same way.

After any change, run:

```
python src/build_ground_truth.py
```

This checks the annotation file and rebuilds every file in `data/benchmark/`.

---

## 1. What is annotated

All 309 reviews are annotated:

| Review set | File | Reviews | Used for |
|---|---|---|---|
| Representative | `data/processed/selected_reviews.csv` | 300 (100 per listing) | All prevalence statistics |
| Challenge | `data/processed/challenge_reviews.csv` | 9 | Concerns that must be preserved when these reviews are included in a scenario |

The challenge reviews are annotated with exactly the same rules. They are never counted in prevalence shares.

---

## 2. File format

`annotations.csv` has **one row per piece of evidence**, not one row per review.

| Column | Required | Content |
|---|---|---|
| `review_id` | Yes | The review's `id` from the review files |
| `aspect` | Yes | One of the 11 aspect keys (Section 3) |
| `sentiment` | Yes | `positive`, `negative`, `neutral`, or `mixed` |
| `issue` | No | An issue code from Section 6, for problems and caveats only |
| `evidence` | Yes | An exact quotation from the review |

Example (some of the rows for review 234396800):

```
review_id,aspect,sentiment,issue,evidence
234396800,noise,positive,,"It's nice and quiet"
234396800,comfort,negative,bed_discomfort,"The bed was not the most comfortable"
234396800,comfort,positive,,"there were plenty of blankets and pillows and a space heater for added comfort"
234396800,value,positive,,"The stay was very cost effective"
```

Put the evidence in double quotes. If a quotation contains a double quote, write it twice (`""fraternity""`).

---

## 3. Aspect taxonomy

| Key | Label | Covers | Importance |
|---|---|---|---|
| `cleanliness` | Cleanliness | How clean the space, bedding and bathroom were, including smells and pests | High |
| `location` | Location | Distance to attractions, walkability, neighborhood, views and scenery | Low |
| `host_communication` | Host communication and hospitality | Responsiveness, helpfulness, recommendations, welcome gestures, disputes | Medium |
| `check_in` | Check-in and access | Finding the property, instructions, entry, private entrances, getting from parking to the door | Medium |
| `listing_accuracy` | Listing accuracy | Whether the property matched its description, photos or reasonable expectations | High |
| `comfort` | Comfort | Beds, furniture, space, temperature, light, decor, overall comfort | Medium |
| `amenities` | Amenities | Wi-Fi, appliances, kitchen, supplies, parking, outdoor spaces, plumbing | Medium |
| `noise` | Noise | Quiet or noise from streets, neighbors, the host's household or surroundings | High |
| `value` | Value | Whether the stay was worth the price | Low |
| `safety` | Safety, security and privacy | Locks, window coverings, shared internal access, how safe the area felt | High |
| `other` | Other | General appreciation of privacy and seclusion; anything that fits nowhere else | Low |

Importance describes how consequential it would be for a summary to leave out a complaint about that aspect. It is used to select minority concerns (Section 8).

### Decision rules for borderline cases

**Cleanliness**
- Insects and pests are cleanliness: "Hope you like spiders! We saw 2 in the bathroom."
- Pleasant smells count as cleanliness: "the place smelled ever so lovely".

**Location**
- Views and scenery are location: "beautiful view from the porch".
- The porch or deck itself, as a feature of the unit, is amenities: "We loved the sitting area on the deck!"
- A road or drive to the property that is difficult is check-in and access, not location.

**Host communication**
- General praise of the hosts goes here: "Great hosts."
- Welcome gestures and local tips go here: "Brady provides a useful town guide in a binder".
- Supplies the host stocked (toiletries, coffee) are amenities.

**Check-in and access**
- Directions and finding the address go here: "We found the house numbering a bit confusing".
- A private or separate entrance is access: "Separate entrance made it easier to go in and out".
- Physical access counts here, including steep drives, steep walks from parking and tight passages to the door: "The walk up the hill from parking area can be challenging for older people."

**Listing accuracy**
- "As described", "as advertised", "looked just like the photos" are positive listing accuracy.
- An important part of the setup that was not disclosed is negative listing accuracy, even if the guest discovered it rather than being misled. Example: "the apartment is really one side of Christal's home and that the walls are quite thin".

**Comfort**
- Space, coziness, decor and how homey a place feels are comfort: "The room is really spacious and cozy."
- Temperature is comfort: "We could not control the temperature in the room".
- A space heater described as keeping guests warm is comfort. A space heater listed among supplies is amenities.

**Amenities**
- Parking is amenities: "Parking was easy."
- Statements that a place is basic or has no frills are **neutral** amenities: "Fairly standard, no frills basement apartment."

**Noise**
- "Quiet", "peaceful", "tranquil" and "peace and quiet" are **positive** noise, because they describe the absence of disturbance.
- "Slept peacefully" describes sleep quality and is comfort, not noise.

**Value**
- Only label value when the guest judges the price ("great value", "affordable", "worth the money").
- A price that is merely stated is not labelled.

**Safety**
- Locks, unlocked doors or windows, and missing curtains or blinds are safety: "there are no curtains or blinds".
- A neighborhood described as safe is positive safety: "The area felt safe".
- A general liking for a private or secluded place is **other**, not safety: "Very private area."

**Other**
- Use sparingly.
- Praise with no specific aspect ("Awesome place!") is not labelled at all (see Section 7).

---

## 4. Sentiment labels

| Label | Use when | Example |
|---|---|---|
| `positive` | The guest is satisfied with the aspect | "The bed was super comfortable." |
| `negative` | The guest reports a problem, complaint or disappointment, however mild | "we were supplied only two towels" |
| `neutral` | The guest states a fact or caveat without clear praise or complaint | "Basic place for price conscience travellers." |
| `mixed` | A single statement contains both praise and criticism of the same aspect | "cheaply priced but you get what you pay for" |

Rules:

- **Label what the guest says, not how serious you think it is.** A complaint the guest calls minor is still negative: "That it was not lockable, did bother my wife a bit".
- **A caveat followed by "but it didn't bother us" is still recorded.** Use negative if the guest describes it as a drawback, neutral if they only mention it as information.
- **Prefer separate rows over `mixed`.** If the praise and criticism are in different sentences, add one positive row and one negative row. Use `mixed` only when one quotation contains both and cannot be split.
- **Issues are never positive.** A row with an issue code must be negative, neutral or mixed.

### How several rows for the same aspect combine

The script merges all rows for one aspect in one review into a single aspect-level sentiment:

| Rows for the aspect | Combined sentiment |
|---|---|
| Positive and negative (or any `mixed`) | `mixed` |
| Positive, with or without neutral | `positive` |
| Negative, with or without neutral | `negative` |
| Neutral only | `neutral` |

For review 234396800 above, comfort becomes **mixed** (a negative row about the bed, a positive row about the blankets).

---

## 5. Evidence

- **Copy the text exactly.** The script stops with an error if a quotation is not found in its review.
- The match ignores capital letters, extra spaces, `<br/>` line breaks, and curly versus straight quotation marks. Everything else, including spelling mistakes in the review, must match. For example, "plenty of peace and quite" must keep the misspelling.
- **Keep quotations short**: usually one clause or sentence that shows the aspect and sentiment on its own.
- **One statement per row.** If a review praises cleanliness twice, add two rows.
- **The same quotation can support several aspects.** "clean, roomy and a great value." is used for cleanliness, comfort and value in three rows.
- Do not paraphrase, shorten with "...", or join text from different parts of the review.

---

## 6. Issue codes

Add an issue code when a guest reports a **specific problem or caveat**. Leave it blank for praise.

- An issue code must be listed below and must be recorded under its aspect.
- Use the existing code if the problem matches one; do not create a near-duplicate.
- A neutral caveat can carry an issue code: "FYI-Driveway is steep" is `check_in`, `neutral`, `steep_access`.

| Issue code | Aspect | Description |
|---|---|---|
| `unlockable_entrance` | safety | Guest entrance cannot be locked |
| `unlockable_windows` | safety | Windows cannot be locked |
| `no_window_coverings` | safety | No curtains or blinds, leaving guests without privacy from outside |
| `shared_internal_access` | safety | Internal doors, laundry or garage give other occupants access to the guest space |
| `pests_insects` | cleanliness | Spiders, ants or other insects in the unit |
| `poor_cleanliness` | cleanliness | Dirty surfaces, bedding or bathroom; mildew; musty smells |
| `noise_from_adjoining_residence` | noise | Footsteps, music, pets or other noise from the attached home or upstairs occupants |
| `listing_mismatch` | listing_accuracy | Features or photos in the listing do not match the property |
| `layout_not_disclosed` | listing_accuracy | An important feature of the setup (shared walls, known recurring problems) was not disclosed |
| `bed_discomfort` | comfort | Bed is uncomfortable or sags |
| `temperature_control` | comfort | Guests cannot control the temperature, or the unit is too cold or too warm |
| `worn_or_dated_furnishings` | comfort | Worn, torn, run-down or dated furniture and decor |
| `small_bathroom` | comfort | Bathroom is small |
| `low_natural_light` | comfort | Little natural light |
| `neighbor_light_disturbance` | comfort | Outside lighting from a neighboring property disturbs sleep |
| `basic_for_extended_stays` | comfort | Suitable for sleeping only, not for spending time in |
| `steep_access` | check_in | Steep drive, driveway or walk from parking; may be difficult for older or less mobile guests (treated as high importance) |
| `narrow_door_access` | check_in | Tight passage between the stairs and the wall to reach the door |
| `hard_to_find` | check_in | Address numbering or GPS directions are confusing |
| `parking_conditions` | amenities | Parking on grass, far from the door, blocked by others, or a broken parking pass |
| `insufficient_supplies` | amenities | Too few towels, no soap or other missing basics |
| `plumbing_water_pressure` | amenities | Weak water pressure or toilet back-up |
| `hot_water_bath` | amenities | Bathtub water does not get hot |
| `odd_kitchen_layout` | amenities | Kitchen is organized in an inconvenient way |
| `minor_maintenance` | amenities | Small fixtures in need of repair |
| `refund_dispute` | host_communication | Host refused a refund request |
| `host_unresponsive_or_rude` | host_communication | Host was unhelpful, unavailable, dismissive or rude |
| `neighborhood_in_transition` | location | Some nearby properties are run down or under renovation (treated as medium importance) |

To add a new issue code, add it to `ISSUE_CATALOG` in `src/build_ground_truth.py` first, with its aspect and a description. Otherwise the script will reject it.

---

## 7. What not to annotate

- Prices or fees that are only stated, without a judgment.
- Guests' travel plans or reasons for visiting ("We were taking a 9 HR drive with our two year old").
- Thank-you messages and intentions to return ("Thanks Allison and Peter!", "Would stay again").
- General praise that names no specific aspect ("Awesome place!", "Everything went well.").
- Recommendations for local businesses that say nothing about the property ("We highly recommend eating at Zambra!").
- Weather and events unrelated to the stay.

A review that contains only this kind of content gets no rows. It is still kept in the ground truth with an empty aspect list and still counts in its listing's total of 100 representative reviews, so mention shares are not inflated. Of the 300 representative reviews, 17 currently have no rows (5, 3 and 9 for the three listings). The script reports this number on every run.

---

## 8. How the annotations are used

The script derives the following from the annotations. You do not edit these directly; change the annotations and rerun the script.

**Prevalence bands** (share of the listing's 100 representative reviews mentioning an aspect):

| Share | Band |
|---|---|
| Below 10% | Rare |
| 10% to 29% | Occasional |
| 30% to 59% | Common |
| 60% or higher | Widespread |

These are project-specific categories, not Airbnb thresholds.

**Periods:** reviews from 2024 to 2026 (the last three years in the data) are *recent*; earlier reviews are *historical*. Each issue records its first and last mention.

**Important aspects** (used for aspect coverage): an aspect is important for a listing if at least 10% of its representative reviews mention it, or if any review raises a concern about it.

**Minority concerns:** an issue is a minority concern if fewer than 30% of the representative reviews mention it. It is kept as an *important* minority concern if:

- it belongs to a high-importance aspect (cleanliness, listing accuracy, noise, safety) or is `steep_access`; or
- it belongs to a medium-importance aspect and at least two different reviews (representative or challenge) mention it.

Frequency alone does not decide importance: one credible safety complaint is kept, while one comment about a small bathroom is not.

---

## 9. Checks run on every build

The script stops and lists every problem if any of the following is true:

- A `review_id` is not in the review files.
- An aspect, sentiment or issue code is not one of the allowed values.
- An issue code is recorded under a different aspect from the one in Section 6.
- A row with an issue code has a `positive` sentiment.
- A row has no evidence.
- A quotation does not appear in its review.

Fix the listed rows in `annotations.csv` and run the script again.
