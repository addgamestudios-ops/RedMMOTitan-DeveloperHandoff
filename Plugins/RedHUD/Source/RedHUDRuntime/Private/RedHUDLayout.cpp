#include "RedHUDLayout.h"

namespace
{
    const TMap<FName, FRedHUDRect> GRedHUDRects =
    {
        { TEXT("TopProgress"),       FRedHUDRect(1390,  34, 1060,  36, 10) },
        { TEXT("Minimap"),           FRedHUDRect(3245,  25,  567, 562, 20) },

        { TEXT("PartyRow01"),        FRedHUDRect(  42, 300,  274,  65, 20) },
        { TEXT("PartyRow02"),        FRedHUDRect(  42, 377,  276,  67, 20) },
        { TEXT("PartyRow03"),        FRedHUDRect(  42, 457,  274,  66, 20) },

        { TEXT("BuffRow01"),         FRedHUDRect( 101, 840,  549, 110, 21) },
        { TEXT("BuffRow02"),         FRedHUDRect(  99, 957,  551, 115, 21) },
        { TEXT("BuffRow03"),         FRedHUDRect( 101,1083,  549, 112, 21) },

        { TEXT("Consumable01"),      FRedHUDRect(  92,1272,  170, 220, 22) },
        { TEXT("Consumable02"),      FRedHUDRect( 289,1281,  172, 213, 22) },
        { TEXT("Consumable03"),      FRedHUDRect( 487,1281,  170, 211, 22) },

        { TEXT("PlayerStatus"),      FRedHUDRect(  40,1995,  673, 121, 30) },
        { TEXT("ComboPrompt"),       FRedHUDRect( 126,1852,  478, 129, 31) },
        { TEXT("QuestPanel"),        FRedHUDRect( 921,1820,  889, 211, 31) },

        { TEXT("EnemyNameplate"),    FRedHUDRect(2505, 365,  502,  78, 40) },
        { TEXT("Reticle"),           FRedHUDRect(1745, 797,  367, 372, 50) },

        { TEXT("WeaponSlot01"),      FRedHUDRect(2980,1985,  177, 125, 35) },
        { TEXT("WeaponSlot02"),      FRedHUDRect(3160,1987,  176, 123, 35) },

        { TEXT("AbilityUltimate"),   FRedHUDRect(3227, 858,  418, 459, 35) },
        { TEXT("AbilityLeft"),       FRedHUDRect(3043,1175,  315, 337, 35) },
        { TEXT("AbilityRight"),      FRedHUDRect(3493,1189,  315, 324, 35) },
        { TEXT("AbilityBottom"),     FRedHUDRect(3261,1380,  335, 409, 35) },
        { TEXT("GlyphLB"),           FRedHUDRect(3296,1735,   99,  64, 36) },
        { TEXT("GlyphPlus"),         FRedHUDRect(3406,1738,   37,  55, 36) },
        { TEXT("GlyphRB"),           FRedHUDRect(3459,1735,  103,  64, 36) },

        { TEXT("AbilityKeyboard"),   FRedHUDRect(3415,1470,  383, 471, 35) },

        { TEXT("UtilityE"),          FRedHUDRect(3430,2060,   89,  92, 36) },
        { TEXT("UtilityF"),          FRedHUDRect(3528,2059,   89,  93, 36) },
        { TEXT("UtilityG"),          FRedHUDRect(3626,2060,   90,  93, 36) },
        { TEXT("UtilityM"),          FRedHUDRect(3722,2059,   91,  94, 36) },

        { TEXT("ReferenceOverlay"),  FRedHUDRect(   0,   0, 3840,2160,999) }
    };
}

const FRedHUDRect& RedHUDLayout::Get(const FName ElementName)
{
    if (const FRedHUDRect* Found = GRedHUDRects.Find(ElementName))
    {
        return *Found;
    }

    static const FRedHUDRect Fallback(0, 0, 32, 32, 0);
    ensureMsgf(false, TEXT("RED HUD layout element '%s' was not found."), *ElementName.ToString());
    return Fallback;
}

bool RedHUDLayout::Contains(const FName ElementName)
{
    return GRedHUDRects.Contains(ElementName);
}
