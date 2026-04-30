# Coffee Bean Defect Annotation Guide

> HUSKY-SORTER-001 | ML Training Pipeline
> Purpose: Human annotation protocol for labeling real bean images
> Tools: LabelImg (local) or CVAT (cloud/team)

---

## Annotation Task

Label each coffee bean image as one of **14 classes**:

| Class ID | Name | Label | Action | Key Visual Indicators |
|----------|------|-------|--------|------------------------|
| 0 | `normal` | ✅ Normal | PASS | Uniform green-brown color, smooth surface, typical oval shape |
| 1 | `mold` | ❌ Moldy | REJECT | Blue-green or gray patches, fuzzy texture, white/green spots |
| 2 | `fermented` | ❌ Fermented | REJECT | Brownish-red discoloration, sour smell description, uneven surface |
| 3 | `black` | ❌ Black | REJECT | Dark brown to black, scorched appearance, no green remaining |
| 4 | `broken` | ❌ Broken | REJECT | Chipped/fragmented, exposed interior visible, irregular edge |
| 5 | `foreign` | ❌ Foreign | REJECT | Stone (gray, irregular), twig (brown, elongated), wood chip |
| 6 | `underweight` | ❌ Underweight | REJECT | Severely shriveled, concave surfaces, significantly smaller |
| 7 | `underdeveloped` | ❌ Immature | REJECT | Flat/pencil-shaped, very light weight, pale color |
| 8 | `dead` | ❌ Dead | REJECT | Dark, lifeless, no moisture, hollow-sounding (per notes) |
| 9 | `insect` | ❌ Insect | REJECT | Holes, channels, brown tunnels visible on surface |
| 10 | `hollow` | ❌ Hollow | REJECT | Visible cavity/crack through bean, different sound (if tapped) |
| 11 | `over_dry` | ❌ Over-dried | REJECT | Visible cracks, very light, parchment easily detached |
| 12 | `over_wet` | ❌ Over-wet | REJECT | Dark, moist sheen, risk of mold, clumped appearance |
| 13 | `pre_mold` | ❌ Pre-mold | REJECT | Early discoloration, slight off-color patches, monitor closely |

---

## Dual Image Annotation

Each bean is photographed from **top** and **bottom** by two cameras:
- **Top image**: HQ Camera IMX477 (main classifier)
- **Bottom image**: USB Camera C270

**Annotation rule:**
- If EITHER top OR bottom shows a defect → label = that defect class
- Use the WORSE defect if multiple present (e.g., mold + broken → `mold`)
- Annotate BOTH images with the SAME label (they are the same bean)

---

## Confidence Rating

For each annotation, rate your confidence:
- **High (1.0)**: Defect clearly visible, unambiguous
- **Medium (0.7-0.9)**: Some ambiguity, partial view, multiple defects competing
- **Low (0.5-0.7)**: Very hard to tell, borderline case

---

## Common Confusion Cases

### Normal vs. Pre-Mold (class 13)
- Normal: Color is uniform, consistent green-brown
- Pre-mold: Small patches of slightly different color, early stage

### Normal vs. Underdeveloped (class 7)
- Normal: Full oval shape, typical size (~1cm long)
- Underdeveloped: Flat, pencil-shaped, noticeably thinner

### Mold (class 1) vs. Fermented (class 2)
- Mold: Blue-green patches, fuzzy appearance
- Fermented: Brownish-red overall, no fuzzy texture

### Black (class 3) vs. Over-dried (class 11)
- Black: Entire bean is dark brown to black
- Over-dried: Normal color but with visible cracks, light weight

### Broken (class 4) vs. Foreign (class 5)
- Broken: Coffee bean fragment, curved interior visible
- Foreign: Non-coffee material (stone, wood, twig)

---

## LabelImg Usage

```bash
# Install
pip install labelImg

# Launch ( Pascal VOC format → auto-convert to COCO below)
labelImg ./data/beans_real/session_XXXXXXX \
    --_classes normal,mold,fermented,black,broken,foreign,underweight,underdeveloped,dead,insect,hollow,over_dry,over_wet,pre_mold

# Tip: Use 'a' key for next image, 'w' for save
```

## CVAT Setup (Team Annotation)

```bash
# Install CVAT
docker pull cvat/cvat

# Create annotation task with classes
cvat-cli create task \
    --name "coffee_beans_session_001" \
    --classes normal,mold,fermented,black,broken,foreign,underweight,underdeveloped,dead,insect,hollow,over_dry,over_wet,pre_mold \
    ./data/beans_real/session_XXXXXXX/
```

---

## Data Export Format

Annotation output format for pipeline:

```json
{
  "bean_id": "bean_00001",
  "top_image": "./data/beans/session_001/bean_00001_top.png",
  "bottom_image": "./data/beans/session_001/bean_00001_bottom.png",
  "defect_class": 1,
  "class_name": "mold",
  "confidence": 0.9,
  "annotator": "reviewer_01",
  "notes": "Clear blue-green patch visible in top-right quadrant"
}
```

---

## Minimum Training Data Requirements

| Scenario | Normal images | Defect images | Notes |
|----------|--------------|---------------|-------|
| Minimum viable | 500 | 100 per rare class | ⚠️ Low accuracy |
| Production (single-origin) | 2,000 | 300 per class | Target for each coffee variety |
| Multi-origin (full) | 5,000+ | 500 per class | Per variety × process combination |
| Augmentation | Apply 5-10× via `ml_pipeline.py --augmentation` | — | Use when real data scarce |

---

## Quality Assurance Protocol

1. **Double annotation**: 10% of images annotated by two reviewers
2. **Disagreement resolution**: Senior reviewer decides (target: >95% agreement)
3. **Edge cases**: Flag images with confidence <0.7 for review
4. **Class balance check**: Monitor defect rate; if <1%, re-inspect annotation quality
5. **Cross-validation**: Hold out 20% of data for final evaluation (never used in training)

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-30 | v1.0 | Initial annotation guide |
