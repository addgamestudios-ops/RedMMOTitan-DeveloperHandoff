#pragma once

#include "CoreMinimal.h"

struct FRedHUDRect
{
    float X;
    float Y;
    float W;
    float H;
    int32 Z;

    constexpr FRedHUDRect(float InX, float InY, float InW, float InH, int32 InZ)
        : X(InX), Y(InY), W(InW), H(InH), Z(InZ)
    {
    }

    FVector2D Position() const { return FVector2D(X, Y); }
    FVector2D Size() const { return FVector2D(W, H); }
};

namespace RedHUDLayout
{
    inline constexpr float DesignWidth = 3840.0f;
    inline constexpr float DesignHeight = 2160.0f;

    REDHUDRUNTIME_API const FRedHUDRect& Get(const FName ElementName);
    REDHUDRUNTIME_API bool Contains(const FName ElementName);
}
