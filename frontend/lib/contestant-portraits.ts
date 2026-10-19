const SOURCE =
  "https://www.paramountplus.com/sneak-peak/survivor-season-51-cast/";
const IMAGE_BASE =
  "https://www.paramountplus.com/sneak-peak/wp-content/uploads/2026/09/";

// Each URL was linked beside this contestant's name in the official cast announcement.
// Keep identity and season explicit: future seasons must not inherit these photos.
const SEASON_51: Record<string, { fullName: string; image: number }> = {
  US0752: { fullName: "Aaliyah Puglia", image: 87 },
  US0753: { fullName: "Alexis Levine", image: 90 },
  US0754: { fullName: "An “Thien An” Nguyen", image: 88 },
  US0755: { fullName: "Ana Sani", image: 91 },
  US0756: { fullName: "Angelica “Jelly” Loblack", image: 98 },
  US0757: { fullName: "Brady Booker", image: 94 },
  US0758: { fullName: "Carter Krull", image: 95 },
  US0759: { fullName: "Cristian Chavez", image: 97 },
  US0760: { fullName: "Danny “Kilby” Kilby", image: 106 },
  US0761: { fullName: "Devin Way", image: 102 },
  US0762: { fullName: "Eric Macksoud", image: 103 },
  US0763: { fullName: "Jenna Doore", image: 89 },
  US0764: { fullName: "Kristin Flickinger", image: 100 },
  US0765: { fullName: "Lewis Kelly", image: 104 },
  US0766: { fullName: "Linnea Capobianco", image: 93 },
  US0767: { fullName: "Maggie Nestor", image: 92 },
  US0768: { fullName: "Mike Pinsky", image: 96 },
  US0769: { fullName: "Ori Jean-Charles", image: 107 },
  US0770: { fullName: "Patt Cannaday", image: 105 },
  US0771: { fullName: "Rob Antonson", image: 101 },
  US0772: { fullName: "Sharonda Cox", image: 99 }
};

export function getContestantPortrait(season: number, castawayId: string) {
  const portrait =
    season === 51 && Object.hasOwn(SEASON_51, castawayId)
      ? SEASON_51[castawayId]
      : undefined;
  return portrait
    ? {
        fullName: portrait.fullName,
        url: `${IMAGE_BASE}image-${portrait.image}-1024x683.jpeg`,
        source: SOURCE,
        credit: "Photo: CBS / Paramount+"
      }
    : null;
}
