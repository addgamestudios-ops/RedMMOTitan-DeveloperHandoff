#include "RedWorldAssetPalette.h"

bool URedWorldAssetPalette::FindEntry(
	const FName EntryId, FRedWorldAssetPaletteEntry& OutEntry) const
{
	for (const FRedWorldAssetPaletteEntry& Entry : Entries)
	{
		if (Entry.EntryId == EntryId)
		{
			OutEntry = Entry;
			return true;
		}
	}

	return false;
}
