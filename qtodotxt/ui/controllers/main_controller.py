import os
import sys
import argparse

from PySide import QtCore
from PySide import QtGui

from qtodotxt.lib import todolib, settings

from tasks_list_controller import TasksListController
from filters_tree_controller import FiltersTreeController
from qtodotxt.lib.filters import SimpleTextFilter, FutureFilter
from menu_controller import MenuController

FILENAME_FILTERS = ';;'.join([
    'Text Files (*.txt)',
    'All Files (*.*)'])

class MainController(QtCore.QObject):
    def __init__(self, view, dialogs_service, task_editor_service):
        super(MainController, self).__init__()
        self._view = view
        self._dialogs_service = dialogs_service
        self._task_editor_service = task_editor_service
        self._initControllers()
        self._file = todolib.File()
        self._is_modified = False
        self._settings = settings.Settings()
        self._setIsModified(False)
        self._view.closeEventSignal.connect(self._view_onCloseEvent)
        self._args = self._parseArgs()
        timer = QtCore.QTimer(self)
        self.connect(timer, QtCore.SIGNAL("timeout()"), self.autoSave)
        timer.start(10000)

    def autoSave(self):
        if self._settings.getAutoSave():
            self.save()
        
    def _parseArgs(self):
        if len(sys.argv) > 1 and sys.argv[1].startswith('-psn'):
            del sys.argv[1]
        parser = argparse.ArgumentParser(description='QTodoTxt')
        parser.add_argument('-f', '--file', type=str, nargs=1, metavar='TEXTFILE')
        parser.add_argument('-q', '--quickadd', action='store_true', \
                help='opens the add task dialog and exit the application when done')
        return parser.parse_args()
    
    def _initControllers(self):
        self._initFiltersTree()
        self._initTasksList()
        self._initMenuBar()
        self._initFilterText()
    
    def _initMenuBar(self):
        menu = self._view.menuBar()
        self._menu_controller = MenuController(self, menu)

    def exit(self):
        self._view.close()
        sys.exit()

    def getView(self):
        return self._view
    
    def show(self):
        self._view.show()
        self._updateTitle()
        self._settings.load()
        self._updateCreatePref()
        self._updateAutoSavePref()
        self._updateAutoArchivePref()
        self._updateHideFutureTasksPref()

        filename = None
        if self._args.file:
            filename = self._args.file[0]
        else:
            filename = self._settings.getLastOpenFile()

        if filename:
            self.openFileByName(filename)

        if self._args.quickadd:
            self._tasks_list_controller.createTask()
            self.save()
            self.exit()
        
    def _initFiltersTree(self):
        controller = self._filters_tree_controller = \
            FiltersTreeController(self._view.filters_tree_view)
        controller.filterSelectionChanged.connect(
            self._onFilterSelectionChanged)

    def _onFilterSelectionChanged(self, filters):
        # First we filter with filters tree
        treeTasks = todolib.filterTasks(filters, self._file.tasks)
        # Then with our filter text
        filterText = self._view.tasks_view.filter_tasks.getText()
        tasks = todolib.filterTasks([SimpleTextFilter(filterText)],treeTasks)
        # And finally with future filter if needed
        # TODO: refactor all that filters
        if (self._settings.getHideFutureTasks()):
            tasks = todolib.filterTasks([FutureFilter()], tasks)
        self._tasks_list_controller.showTasks(tasks)

    def _initFilterText(self):
        self._view.tasks_view.filter_tasks.filterTextChanged.connect(
            self._onFilterTextChanged)

    def _onFilterTextChanged(self,text):
        # First we filter with filters tree
        filters = self._filters_tree_controller._view.getSelectedFilters()
        treeTasks = todolib.filterTasks(filters,self._file.tasks)
        # Then with our filter text
        tasks = todolib.filterTasks([SimpleTextFilter(text)],treeTasks)
        # And finally with future filter if needed
        # TODO: refactor all that filters
        if (self._settings.getHideFutureTasks()):
            tasks = todolib.filterTasks([FutureFilter()], tasks)
        self._tasks_list_controller.showTasks(tasks)
        
    def _initTasksList(self):
        controller = self._tasks_list_controller = \
            TasksListController(self._view.tasks_view.tasks_list_view, self._task_editor_service)
        
        controller.taskCreated.connect(self._tasks_list_taskCreated)
        controller.taskModified.connect(self._tasks_list_taskModified)
        controller.taskDeleted.connect(self._tasks_list_taskDeleted)
        controller.taskArchived.connect(self._tasks_list_taskArchived)

    def _tasks_list_taskDeleted(self, task):
        self._file.tasks.remove(task)
        self._onFileUpdated()

    def _tasks_list_taskCreated(self, task):
        self._file.tasks.append(task)
        self._onFileUpdated()
    
    def _tasks_list_taskModified(self, task):
        self._onFileUpdated()

    def _tasks_list_taskArchived(self, task):
        self._file.saveDoneTask(task)
        self._file.tasks.remove(task)
        self._onFileUpdated()
        
    def _onFileUpdated(self):
        self._filters_tree_controller.showFilters(self._file)
        self._task_editor_service.updateValues(self._file)
        self._setIsModified(True)


 
    def _canExit(self):
        if not self._is_modified:
            return True
        button = self._dialogs_service.showSaveDiscardOrCancel('Unsaved changes...')
        if button == QtGui.QMessageBox.Save:
            self.save()
            return True
        else:
            return button == QtGui.QMessageBox.Discard
        
    def _view_onCloseEvent(self, closeEvent):
        if self._canExit():
            closeEvent.accept()
        else:
            closeEvent.ignore()

    def _setIsModified(self, is_modified):
        self._is_modified = is_modified
        self._updateTitle()
        self._menu_controller.saveAction.setEnabled(is_modified)
        self._menu_controller.revertAction.setEnabled(is_modified)
        
    def save(self):
        if self._file.filename:
            self._file.save()
            self._setIsModified(False)
        else:
            (filename, ok) = \
                QtGui.QFileDialog.getSaveFileName(self._view, filter=FILENAME_FILTERS)
            if ok and filename:
                self._file.save(filename)
                self._settings.setLastOpenFile(filename)
                self._setIsModified(False)     
                
    def _updateTitle(self):
        title = 'QTodoTxt - '
        if self._file.filename:
            filename = os.path.basename(self._file.filename)
            title += filename
        else:
            title += 'Untitled'
        if self._is_modified:
            title += ' (*)'
        self._view.setWindowTitle(title)
           
    def open(self):
        (filename, ok) = \
            QtGui.QFileDialog.getOpenFileName(self._view, filter=FILENAME_FILTERS)
        
        if ok and filename:
            self.openFileByName(filename)
            
    def new(self):
        if self._canExit():
            self._openFile(todolib.File())

    def revert(self):
        if self._dialogs_service.showConfirm('Revert to saved file (and lose unsaved changes)?'):
            self.openFileByName(self._file.filename)

    def openFileByName(self, filename):
        file = todolib.File()
        try:
            file.load(filename)
        except todolib.ErrorLoadingFile as ex:
            self._dialogs_service.showError(str(ex))
            return
        self._openFile(file)
        self._settings.setLastOpenFile(filename)
        
    def _openFile(self, file):
        self._file = file
        self._setIsModified(False)
        self._filters_tree_controller.showFilters(file)
        self._task_editor_service.updateValues(file)

    def _updateCreatePref(self):
        self._menu_controller.changeCreatedDateState(bool(self._settings.getCreateDate()))

    def _updateAutoSavePref(self):
        self._menu_controller.changeAutoSaveState(bool(self._settings.getAutoSave()))
        
    def _updateAutoArchivePref(self):
        self._menu_controller.changeAutoArchiveState(bool(self._settings.getAutoArchive()))

    def _updateHideFutureTasksPref(self):
        self._menu_controller.changeHideFutureTasksState(bool(self._settings.getHideFutureTasks()))

    def createdDate(self):
        if self._settings.getCreateDate():
            self._settings.setCreateDate(False)
        else:
            self._settings.setCreateDate(True)

    def toggleAutoSave(self):
        if self._settings.getAutoSave():
            self._settings.setAutoSave(False)
        else:
            self._settings.setAutoSave(True)
            
    def toggleAutoArchive(self):
        if self._settings.getAutoArchive():
            self._settings.setAutoArchive(False)
        else:
            self._settings.setAutoArchive(True)

    def toggleHideFutureTasks(self):
        if self._settings.getHideFutureTasks():
            self._settings.setHideFutureTasks(False)
        else:
            self._settings.setHideFutureTasks(True)
        self._onFilterSelectionChanged(self._filters_tree_controller._view.getSelectedFilters())

    def toggleVisible(self):
        if self._view.isMinimized():
            self._view.showNormal()
            self._view.activateWindow()
        else:
            self._view.showMinimized()

