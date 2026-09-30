import React, { useState } from 'react';
import { GanttTask } from '../../types';
import { Calendar, Filter, User, CheckCircle2, Clock, ChevronRight } from 'lucide-react';
import { Modal } from '../common/Modal';

export const GanttTimeline: React.FC = () => {
  const [tasks, setTasks] = useState<GanttTask[]>([]);
  const [deptFilter, setDeptFilter] = useState('all');
  const [viewMode, setViewMode] = useState<'week' | 'month' | 'quarter'>('month');
  const [selectedTask, setSelectedTask] = useState<GanttTask | null>(null);

  const filteredTasks = tasks.filter(t => {
    if (deptFilter !== 'all' && t.departmentId !== deptFilter) return false;
    return true;
  });

  // Timeline columns simulation (Month: Sep 1 to Sep 30)
  const days = Array.from({ length: 30 }, (_, i) => i + 1);

  const getTaskCoordinates = (start: string, end: string) => {
    // Parse day of September
    const startDay = parseInt(start.split('-')[2]) || 1;
    const endDay = parseInt(end.split('-')[2]) || 30;
    const leftPercent = ((startDay - 1) / 30) * 100;
    const widthPercent = Math.max(8, ((endDay - startDay + 1) / 30) * 100);
    return { leftPercent, widthPercent };
  };

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-gray-900">Operations Timeline</h2>
          <p className="text-xs text-[#848485]">Multi-department schedule and execution velocity</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Department Filter */}
          <select
            value={deptFilter}
            onChange={e => setDeptFilter(e.target.value)}
            className="text-xs bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-gray-700 focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          >
            <option value="all">All Departments</option>
            <option value="dept-sales-1">Sales 1</option>
            <option value="dept-sales-2">Sales 2</option>
            <option value="dept-email-mktg">Email Marketing</option>
          </select>

          {/* View Mode Toggle */}
          <div className="flex items-center bg-[#F8F9FA] p-0.5 rounded-lg border border-[#E5E7EB] text-xs">
            {(['week', 'month', 'quarter'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`px-3 py-1 rounded-md font-medium capitalize transition-all ${
                  viewMode === mode
                    ? 'bg-[#2D4351] text-white shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Gantt Timeline Board */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[800px]">
            {/* Timeline Header Days */}
            <div className="grid grid-cols-12 border-b border-[#E5E7EB] bg-[#F8F9FA] text-[11px] font-semibold text-[#848485]">
              <div className="col-span-4 p-3 border-r border-[#E5E7EB]">Task & Owner</div>
              <div className="col-span-8 p-3 flex justify-between items-center text-xs">
                <span>Sep 1</span>
                <span>Sep 8</span>
                <span>Sep 15</span>
                <span>Sep 22</span>
                <span>Sep 30</span>
              </div>
            </div>

            {/* Task Rows */}
            <div className="divide-y divide-gray-100">
              {filteredTasks.length === 0 ? (
                <div className="py-12 text-center text-xs text-gray-400">
                  No operational tasks scheduled on timeline.
                </div>
              ) : (
                filteredTasks.map(task => {
                const { leftPercent, widthPercent } = getTaskCoordinates(task.startDate, task.endDate);

                return (
                  <div
                    key={task.id}
                    onClick={() => setSelectedTask(task)}
                    className="grid grid-cols-12 items-center hover:bg-gray-50/80 cursor-pointer transition-colors group py-2"
                  >
                    {/* Task Info Column */}
                    <div className="col-span-4 px-3 border-r border-[#E5E7EB]">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-900 truncate">
                          {task.name}
                        </span>
                        <span className="text-[10px] text-gray-500 font-mono">
                          {task.progress}%
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-[#848485] mt-0.5">
                        <span className="truncate">{task.owner}</span>
                        <span>•</span>
                        <span className="text-gray-600 font-medium">{task.departmentName}</span>
                      </div>
                    </div>

                    {/* Timeline Bar Column */}
                    <div className="col-span-8 px-3 relative h-10 flex items-center">
                      <div
                        className="absolute h-7 rounded-lg bg-[#2D4351] text-white flex items-center px-2.5 shadow-sm overflow-hidden hover:brightness-110 transition-all"
                        style={{
                          left: `${leftPercent}%`,
                          width: `${widthPercent}%`,
                        }}
                      >
                        {/* Progress Fill inside bar */}
                        <div
                          className="absolute inset-0 bg-emerald-600/30"
                          style={{ width: `${task.progress}%` }}
                        />
                        <span className="relative text-[11px] font-medium truncate z-10">
                          {task.category} ({task.progress}%)
                        </span>
                      </div>
                    </div>
                  </div>
                );
              }))}
            </div>
          </div>
        </div>
      </div>

      {/* Task Detail Modal */}
      {selectedTask && (
        <Modal
          isOpen={!!selectedTask}
          onClose={() => setSelectedTask(null)}
          title={selectedTask.name}
          subtitle={`Department: ${selectedTask.departmentName}`}
        >
          <div className="space-y-3.5">
            <div className="p-3 bg-[#F8F9FA] rounded-lg border border-[#E5E7EB] space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">Owner</span>
                <span className="font-semibold text-gray-900">{selectedTask.owner}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Category</span>
                <span className="font-semibold text-gray-900">{selectedTask.category}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Schedule</span>
                <span className="font-semibold text-gray-900">
                  {selectedTask.startDate} to {selectedTask.endDate}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <span className="font-semibold text-emerald-700">{selectedTask.status}</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold mb-1">
                <span>Task Execution Progress</span>
                <span>{selectedTask.progress}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-[#2D4351] h-full rounded-full"
                  style={{ width: `${selectedTask.progress}%` }}
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedTask(null)}
                className="px-4 py-1.5 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
