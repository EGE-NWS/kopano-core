/*
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright 2005 - 2016 Zarafa and its licensors
 */
#pragma once
#include <kopano/zcdefs.h>
#include <condition_variable>
#include <list>
#include <mutex>
#include <mapi.h>
#include <mapix.h>
#include <mapidefs.h>
#include <kopano/ECUnknown.h>
#include <kopano/Util.h>
#include <kopano/memory.hpp>

namespace KC {

class KC_EXPORT MAPINotifSink KC_FINAL_OPG : public IMAPIAdviseSink {
public:
    static HRESULT Create(MAPINotifSink **lppSink);
	KC_HIDDEN virtual ULONG AddRef() KC_OVERRIDE;
	virtual ULONG Release() KC_OVERRIDE;
	KC_HIDDEN virtual HRESULT QueryInterface(REFIID iid, void **iface) KC_OVERRIDE;
	KC_HIDDEN virtual ULONG OnNotify(ULONG n, LPNOTIFICATION notif) KC_OVERRIDE;
	virtual HRESULT GetNotifications(ULONG *n, LPNOTIFICATION *notif, BOOL fNonBlock, ULONG timeout);

private:
	KC_HIDDEN MAPINotifSink() = default;
	KC_HIDDEN virtual ~MAPINotifSink();

	std::mutex m_hMutex;
	std::condition_variable m_hCond;
	std::list<memory_ptr<NOTIFICATION>> m_lstNotifs;
	bool m_bExit = false;
	unsigned int m_cRef = 0;
	ALLOC_WRAP_FRIEND;
};

} /* namespace */
