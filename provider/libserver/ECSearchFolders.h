/*
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright 2005 - 2016 Zarafa and its licensors
 */
#pragma once
#include <kopano/zcdefs.h>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <pthread.h>
#include "ECDatabaseFactory.h"
#include <kopano/ECKeyTable.h>
#include "ECStoreObjectTable.h"
#include "soapH.h"
#include "SOAPUtils.h"
#include <map>
#include <set>
#include <list>
#include "cmd.hpp"

namespace KC {

class ECSessionManager;
class THREADINFO;

struct SEARCHFOLDER final {
	SEARCHFOLDER(unsigned int store_id, unsigned int folder_id) :
		ulStoreId(store_id), ulFolderId(folder_id)
	{}
	~SEARCHFOLDER() {
		soap_del_PointerTosearchCriteria(&lpSearchCriteria);
	}

	struct searchCriteria *lpSearchCriteria = nullptr;
	std::mutex mMutexThreadFree;
	bool bThreadFree = true, bThreadExit = false;
	unsigned int ulStoreId, ulFolderId;
};

struct EVENT {
	unsigned int ulStoreId, ulFolderId, ulObjectId;
    ECKeyTable::UpdateType  ulType;
};

typedef std::map<unsigned int, std::shared_ptr<SEARCHFOLDER>> FOLDERIDSEARCH;
typedef std::map<unsigned int, FOLDERIDSEARCH> STOREFOLDERIDSEARCH;
typedef std::map<unsigned int, pthread_t> SEARCHTHREADMAP;

struct sSearchFolderStats {
	ULONG ulStores, ulFolders, ulEvents;
	ULONGLONG ullSize;
};

/**
 * Searchfolder handler
 *
 * This represents a single manager of all searchfolders on the server; a single thread runs on behalf of this
 * manager to handle all object changes, and another thread can be running for each searchfolder that is rebuilding. Most of
 * the time only the single update thread is running though.
 *
 * The searchfolder manager does four things:
 * - Loading all searchfolder definitions (restriction and folderlist) at startup
 * - Adding and removing searchfolders when users create/remove searchfolders
 * - Rebuilding searchfolder contents (when users rebuild searchfolders)
 * - Getting searchfolder results (when users open searchfolders)
 *
 * Storage of searchresults is on-disk in the MySQL database; restarts of the storage server do not affect searchfolders
 * except rebuilding searchfolders; when the server starts and finds a searchfolder that was only half-built, a complete
 * rebuild is started since we don't know how far the rebuild got last time.
 */
class KC_EXPORT ECSearchFolders final {
public:
	KC_HIDDEN ECSearchFolders(ECSessionManager *, ECDatabaseFactory *);
	KC_HIDDEN virtual ~ECSearchFolders();

    /**
     * Does the initial load of all searchfolders by looking in the hierarchy table for ALL searchfolders and retrieving the
     * information for each of them. Will also rebuild folders that need rebuilding (folders with the REBUILDING state)
     */
    virtual ECRESULT LoadSearchFolders();

    /**
     * Set search criteria for a new or existing search folder
     *
     * Will remove any previous search criteria on the folder, cleanup the search results and rebuild the search results.
     * This function is called almost directly from the SetSearchCriteria() MAPI function.
     *
     * @param[in] ulStoreId The store id (hierarchyid) of the searchfolder being modified
     * @param[in] ulFolderId The folder id (hierarchyid) of the searchfolder being modified
     * @param[in] lpSearchCriteria Search criteria to be set
     */
	KC_HIDDEN virtual ECRESULT SetSearchCriteria(unsigned int store_id, unsigned int folder_id, const struct searchCriteria *);

    /**
     * Retrieve search criteria for an existing search folder
     *
     * @param[in] ulStoreId The store id (hierarchyid) of the searchfolder being modified
     * @param[in] ulFolderId The folder id (hierarchyid) of the searchfolder being modified
     * @param[out] lpSearchCriteria Search criteria previously set via SetSearchCriteria
     */
	KC_HIDDEN virtual ECRESULT GetSearchCriteria(unsigned int store_id, unsigned int folder_id, struct searchCriteria **, unsigned int *search_flags);

    /**
     * Get current search results for a folder. Simply a database query, nothing more.
     *
     * This retrieves all the items that the search folder contains as a list of hierarchy IDs. Since the
     * search results are already available, the data is returned directly from the database.
     *
     * @param[in] ulStoreId The store id (hierarchyid) of the searchfolder being modified
     * @param[in] ulFolderId The folder id (hierarchyid) of the searchfolder being modified
     * @param[out] lstObjIds List of object IDs in the result set. List is cleared and populated.
     */
	KC_HIDDEN virtual ECRESULT GetSearchResults(unsigned int store_id, unsigned int folder_id, std::list<unsigned int> *objids);

    /**
     * Queue a messages change that should be processed to update the search folders
     *
     * This function should be called for any message object that has been modified so that the change can be processed
     * in all searchfolders. You must specify if the item was modified (added) or deleted since delete processing
     * is much simpler (just remove the item from all searchfolders)
     *
     * This function should be called AFTER the change has been written to the database and AFTER the change
     * has been committed, otherwise the change will be invisible to the searchfolder update code.
     *
     * Folder changes never need to be processed since searchfolders cannot be used for other folders
     *
     * @param[in] ulStoreId The store id (hierarchyid) of the object that should be processed
     * @param[in] ulFolderId The folder id (hierarchyid) of the object that should be processed
     * @param[in] ulObjId The hierarchyid of the modified object
     * @param[in] ulType ECKeyTable::TABLE_ROW_ADD or TABLE_ROW_MODIFY or TABLE_ROW_DELETE
     */
	KC_HIDDEN virtual ECRESULT UpdateSearchFolders(unsigned int store_id, unsigned int folder_id, unsigned int obj_id, ECKeyTable::UpdateType);

    /**
     * Remove a search folder because it has been deleted. Cancels the search before removing the information. It will
     * remove all results from the database.
     *
     * This is different from Cancelling a search folder (see CancelSearchFolder()) because the results are actually
     * deleted after cancelling.
     *
     * @param[in] ulStoreId The store id (hierarchyid) of the folder to be removed
     * @param[in] ulFolderId The folder id (hierarchyid) of the folder to be removed
     */
	KC_HIDDEN virtual ECRESULT RemoveSearchFolder(unsigned int store_id, unsigned int folder_id);

	/**
	 * Remove a search folder of a specific store because it has been deleted. Cancels the search before removing the
	 * information. It will remove all results from the database.
	 *
	 * @param[in] ulStoreId The store id (hierarchyid) of the folder to be removed
	 */
	KC_HIDDEN virtual ECRESULT RemoveSearchFolder(unsigned int store_id);

	/**
	 * Wait till all threads are down and free the data of a searchfolder
	 *
	 * @param[in] lpFolder	Search folder data object
	 */
	KC_HIDDEN void DestroySearchFolder(std::shared_ptr<SEARCHFOLDER> &&);

    /**
     * Restart all searches.
     * This is a rather heavy operation, and runs synchronously. You have to wait until it has finished.
     * This is only called with the --restart-searches option of kopano-server and never used in a running
     * system
     */
    virtual ECRESULT RestartSearches();

	/**
	 * Get the searchfolder statistics
	 */
	KC_HIDDEN sSearchFolderStats get_stats();

	/**
	 * Kick search thread to flush events, and wait for the results.
	 * Only used in the test protocol.
	 */
	KC_HIDDEN virtual void FlushAndWait();

private:
    /**
     * Process all events in the queue and remove them from the queue.
     *
     * Events for changed objects are queued internally and only processed after being flushed here. This function
     * groups same-type events together to increase performance because changes in the same folder can be processed
     * more efficiently at on time
     */
	KC_HIDDEN virtual ECRESULT FlushEvents();

    /**
     * Processes a list of message changes in a single folder that should be processed. This in turn
     * will update the search results views through the Table Manager to update the actual user views.
     *
     * @param[in] ulStoreId Store id of the message changes to be processed
     * @param[in] ulFolderId Folder id of the message changes to be processed
     * @param[in] lstObjectIDs List of hierarchyids of messages to be processed
     * @param[in] ulType Type of change: ECKeyTable::TABLE_ROW_ADD, TABLE_ROW_DELETE or TABLE_ROW_MODIFY
     */
	KC_HIDDEN virtual ECRESULT ProcessMessageChange(unsigned int store_id, unsigned int folder_id, ECObjectTableList *objids, ECKeyTable::UpdateType);

    /**
     * Add a search folder to the list of active searches
     *
     * This function add a search folder that should be monitored. This means that changes on objects received via UpdateSearchFolders()
     * will be matched against the criteria passed to this function and processed accordingly.
     *
     * Optionally, a rebuild can be started with the fStartSearch flag. This should be done if the search should be rebuilt, or
     * if this is a new search folder. On rebuild, existing searches for this search folder will be cancelled first.
     *
     * @param[in] ulStoreId Store id of the search folder
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] fStartSearch TRUE if a rebuild must take place, FALSE if not (e.g. this happens at server startup)
     * @param[in] lpSearchCriteria Search criteria for this search folder
     */
	KC_HIDDEN virtual ECRESULT AddSearchFolder(unsigned int store_id, unsigned int folder_id, bool start_search, const struct searchCriteria *);

    /**
     * Cancel a search.
     *
     * This means that the search results are 'frozen'. If a search thread is running, it is cancelled.
     * After a search has been cancelled, we can ignore any updates for that folder, so it is removed from the list
     * of active searches. (but the results remain in the database). We also have to remember this fact in the database because
     * after a server restart, the search should still be 'stopped' and not rebuilt or active.
     *
     * @param[in] ulStoreId Store id of the search folder
     * @param[in] ulFolderId Folder id of the search folder
     */
	KC_HIDDEN virtual ECRESULT CancelSearchFolder(unsigned int store_id, unsigned int folder_id);

    /**
     * Does an actual search for all matching items for a searchfolder
     *
     * Adds information in the database, and sends updates through the table manager to
     * previously opened tables. This is called only from the search thread and from RestartSearches(). After the
     * search is done, changes in the searchfolder are only done incrementally through calls to UpdateSearchFolders().
     *
     * @param[in] ulStoreId Store id of the search folder
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] lpSearchCriteria Search criteria to match
     * @param[in] lpbCancel Pointer to cancel flag. This is polled frequently to be able to cancel the search action
     * @param[in] bNotify If TRUE, send notifications to table listeners, else do not (e.g. when doing RestartSearches())
     */
	KC_HIDDEN virtual ECRESULT Search(unsigned int store_id, unsigned int folder_id, const struct searchCriteria *, bool *cancel, bool notify = true);
	KC_HIDDEN ECRESULT search_r1(ECDatabase *, ECSession *, ECODStore &&, ECCacheManager *, const struct restrictTable *extra_restr, unsigned int store_id, unsigned int folder_id, const std::list<unsigned int> &ix_results, const std::string &sugg, bool notify, bool *cancel);
	KC_HIDDEN ECRESULT search_r2(ECDatabase *, ECSession *, ECODStore &&, const struct searchCriteria *, unsigned int store_id, unsigned int folder_id, const ECListInt &folders, bool notify, bool *cancel);

    /**
     * Get the state of a search folder
     *
     * It may be rebuilding (thread running), running (no thread) or stopped (not active - 'frozen')
     *
     * @param[in] ulStoreId Store id of the search folder
     * @param[in] ulFolderId Folder id of the search folder
     * @param[out] lpulState Current state of folder (SEARCH_RUNNING | SEARCH_REBUILD, SEARCH_RUNNING, 0)
     */
	KC_HIDDEN virtual ECRESULT GetState(unsigned int store_id, unsigned int folder_id, unsigned int *state);

	KC_HIDDEN static void SearchThread(THREADINFO *);

    // Functions to do things in the database

    /**
     * Reset all results for a searchfolder (removes all results)
     *
     * @param[in] ulFolderId Folder id of the search folder
     */
	KC_HIDDEN virtual ECRESULT ResetResults(unsigned int folder_id);

    /**
     * Add a search result to a search folder (one message id with flags)
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] ulObjId Object hierarchy id of the matching message
     * @param[in] ulFlags Flags of the object (this should be in-sync with hierarchy table!). May be 0 or MSGFLAG_READ
     * @param[out] lpfInserted true if a new record was inserted, false if flags were updated in an existing record
     */
	KC_HIDDEN virtual ECRESULT AddResults(unsigned int folder_id, unsigned int obj_id, unsigned int flags, bool *inserted);

    /**
     * Add multiple search results
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] ulObjId Object hierarchy id of the matching message
     * @param[in] ulFlags Flags of the object (this should be in-sync with hierarchy table!). May be 0 or MSGFLAG_READ
     * @param[out] lpulCount Int to be modified with inserted count
     * @param[out] lpulUnread Int to be modified with inserted unread count
     */
	KC_HIDDEN virtual ECRESULT AddResults(unsigned int folder_id, std::list<unsigned int> &obj_id, std::list<unsigned int> &flags, int *count, int *unread);

    /**
     * Delete matching results from a search folder
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] ulObjId Object hierarchy id of the matching message
     * @param[out] lpulFlags Flags of the object that was just deleted
     */
	KC_HIDDEN virtual ECRESULT DeleteResults(unsigned int folder_id, unsigned int obj_id, unsigned int *flags);

    /**
     * Set the status of a searchfolder
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] ulStatus SEARCH_RUNNING or 0
     */
	KC_HIDDEN virtual ECRESULT SetStatus(unsigned int folder_id, unsigned int status);

    // Functions to load/save search criteria to the database

    /**
     * Load serialized search criteria from database
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] lppSearchCriteria Loaded search criteria
     */
	KC_HIDDEN virtual ECRESULT LoadSearchCriteria(unsigned int folder_id, struct searchCriteria **);
	KC_HIDDEN virtual ECRESULT LoadSearchCriteria2(const std::string &, struct searchCriteria **);

    /**
     * Save serialized search criteria to database
     *
     * @param[in] ulFolderId Folder id of the search folder
     * @param[in] lpSearchCriteria Search criteria to save
     */
	KC_HIDDEN virtual ECRESULT SaveSearchCriteria(unsigned int folder_id, const struct searchCriteria *);

    /**
     * Main processing thread entrypoint
     *
     * This thread is running throughout the lifetime of the server and polls the queue periodically to process
     * message changes many-at-a-time.
     *
     * @param[in] lpSearchFolders Pointer to 'this' of search folder manager instance
     */
	KC_HIDDEN static void *ProcessThread(void *search_folders);

	/**
	 * Save search criteria (row) to the database
	 *
	 * Purely writes the given search criteria to the database without any further processing.
	 *
	 * @param[in] lpDatabase Database handle
	 * @param[in] ulFolderId Folder id (hierarchy id) of the searchfolder to write
	 * @param[in] lpSearchCriteria Search criteria to write
	 */
	KC_HIDDEN static ECRESULT SaveSearchCriteriaRow(ECDatabase *, unsigned int folder_id, const struct searchCriteria *);

    /**
     * Process candidate rows and add them to search folder results
     *
     * This function processes the list of rows provides against the restriction provides, and
     * adds rows to the given folder's result set if the rows match. Each row is evaluated separately.
     *
     * @param[in] lpDatabase Database handle
     * @param[in] lpSession Session handle
     * @param[in] lpRestrict Restriction to match the items with
     * @param[in] lpbCancel Pointer to cancellation boolean; processing is stopped when *lpbCancel == true
     * @param[in] ulStoreId Store in which the items in ecRows reside
     * @param[in] ulFolder The hierarchy of the searchfolder to update with the results
     * @param[in] ecODStore Store information
     * @param[in] ecRows Rows to evaluate
     * @param[in] lpPropTags List of precomputed property tags that are needed to resolve the restriction. The first property in this array MUST be PR_MESSAGE_FLAGS.
     * @param[in] locale Locale to use for string comparisons in the restriction
     * @param[in] bNotify TRUE on a live system, FALSE if only the database must be updated.
     * @return result
     */
	KC_HIDDEN virtual ECRESULT ProcessCandidateRows(ECDatabase *, ECSession *, const struct restrictTable *r, bool *cancel, unsigned int store_id, unsigned int folder_id, ECODStore *, ECObjectTableList rows, struct propTagArray *tags, const ECLocale &, std::list<unsigned int> &);
	KC_HIDDEN virtual ECRESULT ProcessCandidateRows(ECDatabase *, ECSession *, const struct restrictTable *r, bool *cancel, unsigned int store_id, unsigned int folder_id, ECODStore *, ECObjectTableList rows, struct propTagArray *tags, const ECLocale &);
	KC_HIDDEN virtual ECRESULT ProcessCandidateRowsNotify(ECDatabase *, ECSession *, const struct restrictTable *r, bool *cancel, unsigned int store_id, unsigned int folder_id, ECODStore *, ECObjectTableList rows, struct propTagArray *tags, const ECLocale &);

    // Map StoreID -> SearchFolderId -> SearchCriteria
    // Because searchfolders only work within a store, this allows us to skip 99% of all
    // search folders during UpdateSearchFolders (depending on how many users you have)
	std::recursive_mutex m_mutexMapSearchFolders;
    STOREFOLDERIDSEARCH m_mapSearchFolders;

    // Pthread condition to signal a thread exit
	std::condition_variable m_condThreadExited;

    ECDatabaseFactory *m_lpDatabaseFactory;
    ECSessionManager *m_lpSessionManager;
	KC::ksrv_tpool m_pool;

    // List of change events
    std::list<EVENT> m_lstEvents;
	std::recursive_mutex m_mutexEvents;
	std::condition_variable_any m_condEvents, m_cond_flush;

    // Change processing thread
    pthread_t m_threadProcess;

    // Exit request for processing thread
	bool m_thread_active = false, m_bExitThread = false, m_bRunning = false;

	friend class THREADINFO;
};

} /* namespace */
