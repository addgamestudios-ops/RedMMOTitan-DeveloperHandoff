#include "VibeMMOUIKit.h"

#include "Modules/ModuleManager.h"

class FVibeMMOUIKitModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
	}

	virtual void ShutdownModule() override
	{
	}
};

IMPLEMENT_MODULE(FVibeMMOUIKitModule, VibeMMOUIKit)
